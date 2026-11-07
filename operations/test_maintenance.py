import gzip
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from operations.maintenance import copy_database,backup,prune,cloud_export,health


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.output=io.StringIO();self.capture=redirect_stdout(self.output);self.capture.__enter__()

    def tearDown(self): self.capture.__exit__(None,None,None)
    def test_consistent_backup_includes_committed_wal_and_restores(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'live.sqlite';destination=root/'restored.sqlite'
            writer=sqlite3.connect(source)
            writer.execute('PRAGMA journal_mode=WAL');writer.execute('CREATE TABLE sample (value TEXT)')
            writer.execute('INSERT INTO sample VALUES (?)',('committed-wal-row',));writer.commit()
            before=source.read_bytes()
            copy_database(source,destination)
            self.assertEqual(source.read_bytes(),before)
            with sqlite3.connect(destination) as restored:
                self.assertEqual(restored.execute('SELECT value FROM sample').fetchone()[0],'committed-wal-row')
            self.assertEqual(destination.stat().st_mode & 0o777,0o600)
            writer.close()

    def test_existing_destination_and_symlink_sources_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';destination=root/'keep'
            source.write_text('not a database');destination.write_text('preserve me')
            with self.assertRaises(FileExistsError): copy_database(source,destination)
            self.assertEqual(destination.read_text(),'preserve me')
            link=root/'link';link.symlink_to(source)
            with self.assertRaises(ValueError): copy_database(link,root/'unused')

    def test_snapshot_stays_fixed_while_another_wal_connection_commits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'live.sqlite';destination=root/'backup.sqlite'
            writer=sqlite3.connect(source)
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('CREATE TABLE sample (version INTEGER)')
            writer.execute('INSERT INTO sample VALUES (1)');writer.commit()
            commits=[]
            real_connect=sqlite3.connect
            class PinnedReader(sqlite3.Connection):
                def execute(self,sql,*args,**kwargs):
                    result=super().execute(sql,*args,**kwargs)
                    if self.in_transaction and sql.startswith('SELECT') and not commits:
                        # The read snapshot is established, but the writer
                        # must still be able to commit a newer version.
                        writer.execute('UPDATE sample SET version=2');writer.commit();commits.append(True)
                    return result
            def connect(path,*args,**kwargs):
                if kwargs.get('uri'): kwargs['factory']=PinnedReader
                return real_connect(path,*args,**kwargs)
            with patch('operations.maintenance.sqlite3.connect',side_effect=connect):
                copy_database(source,destination)
            self.assertTrue(commits)
            self.assertEqual(writer.execute('SELECT version FROM sample').fetchone()[0],2)
            with real_connect(destination) as restored:
                self.assertEqual(restored.execute('SELECT version FROM sample').fetchone()[0],1)
            writer.close()

    def test_backup_set_is_private_checked_and_pruning_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'data.sqlite'
            with sqlite3.connect(source) as db: db.execute('CREATE TABLE sample (value TEXT)')
            folder=root/'ops'/'sqlite'
            manifest=backup(folder,[source],minimum_free=0)
            self.assertTrue(manifest['complete'])
            self.assertEqual(manifest['databases'][0]['restore_quick_check'],'ok')
            self.assertEqual(folder.stat().st_mode & 0o777,0o700)
            unknown=folder/'set-foreign';unknown.mkdir();(unknown/'important').write_text('keep')
            prune(folder,max_sets=0,max_bytes=0)
            self.assertTrue((unknown/'important').exists())
            self.assertEqual(len(list(folder.glob('set-*/manifest.json'))),1)

    def test_cloud_exports_get_only_and_actual_page_sizes_without_credentials_in_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls=[]
            def get(request,timeout):
                calls.append(request)
                self.assertEqual(request.get_method(),'GET')
                self.assertIsNone(request.get_header('Authorization'))
                params=parse_qs(urlsplit(request.full_url).query)
                self.assertTrue('window_start' in params or 'recorded_at' in params)
                return io.BytesIO(json.dumps([{'market_slug':'public-row'}] if params['offset']==['0'] else []).encode())
            with patch.dict('os.environ',SUPABASE_URL='https://fixture.example',SUPABASE_KEY='sb_secret_fixture_not_real'),patch('operations.maintenance.time.sleep'):
                cloud_export(Path(temporary)/'cloud',get=get)
            self.assertEqual(len(calls),6)
            for path in Path(temporary).glob('cloud/set-*/*.gz'):
                with gzip.open(path,'rt') as data: text=data.read()
                self.assertIn('public-row',text);self.assertNotIn('sb_secret',text)

    def test_rotation_removes_only_old_generated_sets_and_preserves_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for index in range(3):
                folder=root/('set-00'+str(index));folder.mkdir()
                (folder/'manifest.json').write_text(json.dumps(dict(format='shaneathon-backup-v1',complete=True)))
                (folder/'data').write_text('fixture')
            foreign=root/'set-foreign';foreign.mkdir();(foreign/'keep').write_text('untouched')
            prune(root,max_sets=2,max_bytes=0)
            self.assertFalse((root/'set-000').exists())
            self.assertTrue((root/'set-001').exists());self.assertTrue((root/'set-002').exists())
            self.assertEqual((foreign/'keep').read_text(),'untouched')

    def test_failed_backup_keeps_last_complete_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'good.sqlite';bad=root/'bad.sqlite'
            with sqlite3.connect(source) as db: db.execute('CREATE TABLE sample (value TEXT)')
            backup(root/'backups',[source],minimum_free=0)
            bad.write_text('not a database')
            with self.assertRaises(sqlite3.DatabaseError): backup(root/'backups',[bad],minimum_free=0)
            self.assertEqual(len(list((root/'backups').glob('set-*/manifest.json'))),1)
            self.assertFalse(list((root/'backups').glob('.incomplete-*')))

    def test_failed_services_are_reported_without_restarting_anything(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch('operations.maintenance.subprocess.run',side_effect=AssertionError('No service mutations allowed')),patch('operations.maintenance.sqlite3.connect',side_effect=sqlite3.OperationalError('fixture unavailable')):
                report=health(temporary,service_check=lambda _:False,publish=False)
            self.assertEqual(report['state'],'CRITICAL')
            self.assertFalse(report['external_notifications_configured'])
            self.assertTrue(any('is not active' in i['message'] for i in report['issues']))
