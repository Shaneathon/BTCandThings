"""Secure server-console configuration. Never paste credentials into chat."""
import argparse
import getpass
import os
from pathlib import Path
from cloud_sync import Client, TABLES


def configure(path, url, key, client_factory=Client):
    if path.exists() or path.is_symlink():
        raise FileExistsError('Existing cloud configuration is never overwritten')
    if any(c in value for value in (url,key) for c in ('\n','\r','\x00')):
        raise ValueError('Multiline configuration is not allowed')
    client=client_factory(url,key)
    # Read-only checks only. A successful read does not prove write permission.
    for table,_ in TABLES.values():
        result=client('GET',table,{'select':'*','limit':'1'})
        if not isinstance(result,list):
            raise ValueError('Research schema or read access unverified')
    def escaped(value):
        return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output:
        output.write('BTC_RESEARCH_SYNC_ENABLED=1\nBTC_RESEARCH_SUPABASE_URL='+escaped(url)+
                     '\nBTC_RESEARCH_SUPABASE_KEY='+escaped(key)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path',type=Path,default=Path('/etc/btcandthings-research.env'))
    parser.add_argument('--from-environment',action='store_true',help='Reuse existing server SUPABASE_URL/KEY without printing them')
    args=parser.parse_args()
    if args.from_environment:
        url=os.environ.get('SUPABASE_URL','').strip()
        key=os.environ.get('SUPABASE_KEY','').strip()
        if not url or not key: parser.error('Existing collector credentials are missing; no file saved')
    else:
        url=input('Supabase project HTTPS URL: ').strip()
        key=getpass.getpass('Server-only Supabase key (hidden): ').strip()
    try:
        configure(args.path,url,key)
    except Exception as exc:
        print('Configuration not saved: '+type(exc).__name__+'. Check schema, access and destination; credentials were not displayed.')
        raise SystemExit(1)
    print('Private server configuration saved. Research-table read access checked; write permission will be checked by synchronization.')


if __name__=='__main__':
    main()
