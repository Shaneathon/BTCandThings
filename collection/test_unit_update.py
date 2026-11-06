import unittest
from unit_update import render


class UnitUpdateTests(unittest.TestCase):
    def setUp(self):
        self.old='/opt/btcandthings-research/releases/old-123'
        self.new='/opt/btcandthings-research/releases/new-456'
        self.text=f'[Service]\nWorkingDirectory={self.old}\nEnvironmentFile=-/etc/btcandthings-research.env\nExecStart={self.old}/venv/bin/python {self.old}/collection/ten_streams.py --db /var/lib/btcandthings-research/research.sqlite --loop --record-available\n'
    def test_only_release_path_changes_preserving_database_and_flags(self):
        result=render(self.text,self.old,self.new)
        self.assertEqual(result,self.text.replace(self.old,self.new))
        self.assertIn('--record-available',result)
        self.assertIn('/etc/btcandthings-research.env',result)
    def test_foreign_paths_rejected(self):
        with self.assertRaises(ValueError): render(self.text,self.old,'/root/BTCandThings')
    def test_unexpected_unit_refused(self):
        with self.assertRaises(ValueError): render('[Service]\nExecStart=/bin/true\n',self.old,self.new)


if __name__=='__main__': unittest.main()
