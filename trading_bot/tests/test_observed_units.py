import unittest
from trading_bot.observed_units import render

class UnitTests(unittest.TestCase):
    def test_only_expected_units_and_ledgers_are_changed(self):
        p,c='/opt/pbot/releases/new','/opt/cbot/releases/new'
        source='WorkingDirectory=/opt/cbot/releases/old\nExecStart=/opt/cbot/releases/old/venv/bin/python -m coinbase_bot.runner --ledger /var/lib/cbot/paper.sqlite --config /etc/cbot-paper.json --tracker-url http://127.0.0.1:8767/status --loop\n'
        result=render('cbot-paper',source,p,c)
        self.assertIn('--ledger /var/lib/cbot/observed-v1.sqlite',result)
        self.assertIn('--observed',result)
        self.assertIn('--config /etc/cbot-paper.json',result)
        self.assertNotIn('releases/old',result)
        with self.assertRaises(ValueError): render('btc-collector',source,p,c)
        with self.assertRaises(ValueError): render('cbot-paper',source.replace('/opt/cbot/releases/old','/tmp/unknown'),p,c)
        with self.assertRaises(ValueError): render('cbot-paper',source.replace('--ledger /var/lib/cbot/paper.sqlite','--ledger /elsewhere'),p,c)
        exporter='WorkingDirectory=/opt/pbot/releases/old\nExecStart=/opt/pbot/releases/old/venv/bin/python -m trading_bot.dual_sandbox export --all-markets\nEnvironmentFile=/root/BTCandThings/collector/.env\n'
        updated=render('pbot-sandbox-input',exporter,p,c)
        self.assertIn('--execution-evidence',updated)
        self.assertIn('EnvironmentFile=/root/BTCandThings/collector/.env',updated)

if __name__=='__main__': unittest.main()
