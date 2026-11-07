"""Pure service rendering for the paper-only migration; never touches services."""
import re


def render(name,text,pbot,cbot):
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    expected='/opt/shaneathon-ops/releases/' if name=='shaneathon-health' else '/opt/cbot/releases/' if name.startswith('cbot') else '/opt/pbot/releases/'
    if not old.startswith(expected) or not re.fullmatch(r'[A-Za-z0-9_-]+',old[len(expected):]):
        raise ValueError('Unexpected unit working directory')
    new=cbot if name.startswith('cbot') else pbot
    text=text.replace(old,new)
    if name=='pbot-paper':
        if ' -m trading_bot.dual_sandbox watch ' not in text: raise ValueError('Unexpected PBot command')
        text='\n'.join('ExecStart='+pbot+'/venv/bin/python -m trading_bot.observed_paper --input /var/lib/pbot-input/dual-sandbox.json --ledger /var/lib/pbot/observed-v1.sqlite --kill-file /var/lib/pbot/STOP-OBSERVED' if line.startswith('ExecStart=') else line for line in text.splitlines())+'\n'
    elif name=='pbot-status':
        if '--ledger /var/lib/pbot/comparison.sqlite' not in text: raise ValueError('Unexpected PBot status ledger')
        text=text.replace('--ledger /var/lib/pbot/comparison.sqlite','--ledger /var/lib/pbot/observed-v1.sqlite')
    elif name=='pbot-sandbox-input':
        if '--all-markets' not in text or '--execution-evidence' in text: raise ValueError('Expected original all-market exporter')
        text='\n'.join(line+' --execution-evidence' if line.startswith('ExecStart=') else line for line in text.splitlines())+'\n'
    elif name in ('cbot-paper','cbot-status'):
        if '--ledger /var/lib/cbot/paper.sqlite' not in text: raise ValueError('Unexpected CBot ledger')
        text=text.replace('--ledger /var/lib/cbot/paper.sqlite','--ledger /var/lib/cbot/observed-v1.sqlite')
        if name=='cbot-paper':
            if '--tracker-url http://127.0.0.1:8767/status' not in text: raise ValueError('Expected existing local tracker')
            text='\n'.join(line+' --observed' if line.startswith('ExecStart=') else line for line in text.splitlines())+'\n'
    elif name not in ('pbot-dashboard','cbot-dashboard','shaneathon-health'):
        raise ValueError('Unrecognized unit')
    return text
