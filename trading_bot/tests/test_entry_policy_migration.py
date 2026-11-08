import json
from pathlib import Path
import tempfile
import unittest
from trading_bot.entry_limits import migrate
from trading_bot.observed_paper import Engine,SETTINGS,PREVIOUS_SETTINGS


class MigrationTests(unittest.TestCase):
    def test_five_dollar_policy_migrates_and_rolls_back_without_erasing_cash_holdings_or_pauses(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'paper.sqlite';engine=Engine(path)
            with engine.db:
                engine.db.execute('UPDATE settings SET payload=?',(json.dumps(PREVIOUS_SETTINGS,sort_keys=True),))
                engine.db.execute("UPDATE wallets SET cash='997' WHERE name='BTC_5m'")
                engine.db.execute("INSERT INTO positions VALUES('BTC_5m','old-open',?)",(json.dumps(dict(state='PAPER_OPEN',cost='3',entry_limits=dict(version=PREVIOUS_SETTINGS['version']))),))
                engine.db.execute("INSERT INTO automatic_entry_pauses VALUES('XRP_5m',1,9999999999,'previous guard')")
                engine.db.execute("INSERT INTO orders VALUES('Champion','unfilled','PROPOSED','{}',NULL)")
            balances=engine.db.execute('SELECT * FROM wallets').fetchall()
            holdings=engine.db.execute('SELECT * FROM positions').fetchall()
            controls=engine.db.execute('SELECT * FROM automatic_entry_pauses').fetchall()
            result=migrate(path)
            self.assertEqual(result['policy']['max_trade_cost'],'1.50')
            self.assertEqual(result['unfilled_proposals_cancelled_without_fee'],1)
            self.assertEqual(engine.db.execute('SELECT * FROM wallets').fetchall(),balances)
            self.assertEqual(engine.db.execute('SELECT * FROM positions').fetchall(),holdings)
            self.assertEqual(engine.db.execute('SELECT * FROM automatic_entry_pauses').fetchall(),controls)
            migrate(path,rollback=True)
            self.assertEqual(json.loads(engine.db.execute('SELECT payload FROM settings').fetchone()[0]),PREVIOUS_SETTINGS)
            self.assertEqual(engine.db.execute('SELECT * FROM positions').fetchall(),holdings)
            engine.close()

    def test_already_current_is_a_noop_and_preserves_current_proposals_and_migration_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'paper.sqlite';engine=Engine(path)
            with engine.db:
                engine.db.execute("INSERT INTO orders VALUES('Champion','current-proposal','PROPOSED','{}',NULL)")
            before=engine.db.execute('SELECT * FROM orders').fetchall()
            result=migrate(path)
            self.assertFalse(result['policy_changed'])
            self.assertEqual(result['unfilled_proposals_cancelled_without_fee'],0)
            self.assertEqual(engine.db.execute('SELECT * FROM orders').fetchall(),before)
            self.assertEqual(engine.db.execute('SELECT count(*) FROM configuration_history').fetchone()[0],0)
            engine.close()

    def test_unknown_policy_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'paper.sqlite';engine=Engine(path)
            with engine.db: engine.db.execute('UPDATE settings SET payload=?',(json.dumps(dict(version='UNKNOWN')),))
            with self.assertRaisesRegex(ValueError,'Unexpected policy'): migrate(path)
            self.assertEqual(json.loads(engine.db.execute('SELECT payload FROM settings').fetchone()[0]),dict(version='UNKNOWN'))
            engine.close()

if __name__=='__main__': unittest.main()
