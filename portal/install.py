"""Install an HTTPS-authenticated portal on an otherwise unused apex host.

Root only, interactive password via controlling terminal. No passwords in
arguments, logs, HTML, Git, or command history. Existing app hosts untouched.
"""
import base64
import getpass
import grp
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

HOST='shaneathon.com'
SITE=Path('/etc/nginx/sites-available')/HOST
ENABLED=Path('/etc/nginx/sites-enabled')/HOST
AUTH=Path('/etc/nginx/shaneathon.htpasswd')
ROOT=Path('/var/www/shaneathon-portal')
ACME=Path('/var/www/shaneathon-acme')
LINKS=Path('/etc/shaneathon-portal-links.json')


def exclusive(path,content,mode=0o644):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    with os.fdopen(fd,'w') as stream: stream.write(content)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def main():
    if os.geteuid()!=0: raise SystemExit('Run as root in the DigitalOcean console.')
    for command in ('nginx','openssl','certbot'):
        if not shutil.which(command): raise SystemExit('Missing required tool: '+command)
    for path in (SITE,ENABLED,AUTH,ROOT,LINKS):
        if path.exists() or path.is_symlink():
            raise SystemExit('Existing '+str(path)+'; refusing replacement. Inspect before retrying.')
    with urlopen('http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address',timeout=5) as response:
        address=response.read(100).decode().strip()
    try:
        addresses={row[4][0] for row in socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM)}
    except socket.gaierror:
        raise SystemExit('Apex DNS is not ready. No portal changes made.')
    if addresses!={address}:
        raise SystemExit('Apex DNS must point exclusively to this droplet. No portal changes made.')
    inspected=subprocess.run(['nginx','-T'],capture_output=True,text=True,check=True).stdout
    for names in re.findall(r'^\s*server_name\s+([^;]+);',inspected,re.MULTILINE):
        if HOST in names.split(): raise SystemExit('An existing apex Nginx host needs review; no files changed.')
    settings=Path('/etc/nginx/nginx.conf').read_text()
    match=re.search(r'^\s*user\s+([\w-]+)(?:\s+([\w-]+))?\s*;',settings,re.MULTILINE)
    if not match: raise SystemExit('Cannot determine Nginx worker identity; no files changed.')
    worker_gid=grp.getgrnam(match[2]).gr_gid if match[2] else pwd.getpwnam(match[1]).pw_gid
    with open('/dev/tty','r+') as terminal:
        if not terminal.isatty(): raise SystemExit('An interactive console is required to keep the password private.')
        terminal.write('Portal username [shane]: ');terminal.flush()
        username=terminal.readline().strip() or 'shane'
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',username): raise SystemExit('Use letters, numbers, dots, underscores or dashes for the username.')
        password=getpass.getpass('Portal password (hidden; at least 12 characters): ',stream=terminal)
        confirmation=getpass.getpass('Repeat portal password: ',stream=terminal)
        if len(password)<12 or password!=confirmation:
            raise SystemExit('Password needs at least 12 characters and both entries must match. No files changed.')
    hashed=subprocess.run(['openssl','passwd','-6','-stdin'],input=password+'\n',text=True,
                          capture_output=True,check=True).stdout.strip()
    if not hashed.startswith('$6$'): raise SystemExit('Password hash generation failed.')
    exclusive(AUTH,username+':'+hashed+'\n',0o640)
    os.chown(AUTH,0,worker_gid)
    exclusive(LINKS,Path(__file__).with_name('links.json').read_text(),0o600)
    ROOT.mkdir(mode=0o750)
    os.chown(ROOT,0,worker_gid)
    subprocess.run([sys.executable,str(Path(__file__).with_name('build.py')),'--links',str(LINKS),'--out',str(ROOT)],check=True)
    for item in ROOT.iterdir():
        os.chown(item,0,worker_gid);item.chmod(0o640)
    ACME.mkdir(parents=True,exist_ok=True)
    http='''server {
    listen 80;
    server_name shaneathon.com;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/shaneathon-acme;
        auth_basic off;
        try_files $uri =404;
    }
    location / { return 301 https://shaneathon.com$request_uri; }
}
'''
    exclusive(SITE,http)
    ENABLED.symlink_to(SITE)
    checked=subprocess.run(['nginx','-t'])
    if checked.returncode:
        ENABLED.unlink()
        raise SystemExit('Portal host validation failed and was disabled. Existing Nginx was not reloaded.')
    subprocess.run(['systemctl','reload','nginx'],check=True)
    subprocess.run(['certbot','certonly','--non-interactive','--webroot','-w',str(ACME),'-d',HOST],check=True)
    https='''server {
    listen 443 ssl;
    server_name shaneathon.com;
    ssl_certificate /etc/letsencrypt/live/shaneathon.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/shaneathon.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    root /var/www/shaneathon-portal;
    index index.html;
    autoindex off;
    auth_basic "Shaneathon private portal";
    auth_basic_user_file /etc/nginx/shaneathon.htpasswd;
    add_header Cache-Control "no-store" always;
    add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'" always;
    location / { try_files $uri $uri/ =404; }
}
'''
    SITE.write_text(http+https)
    if subprocess.run(['nginx','-t']).returncode:
        SITE.write_text(http)
        raise SystemExit('HTTPS configuration failed validation. HTTP still serves no portal content; no reload performed.')
    subprocess.run(['systemctl','reload','nginx'],check=True)
    opener=build_opener(NoRedirect())
    for resource in ('/','/portal.css'):
        for attempt in range(10):
            try:
                with opener.open('https://'+HOST+resource,timeout=10) as response:
                    code=response.status
            except HTTPError as error:
                code=error.code;error.close()
            if code==401: break
            if attempt==9: raise SystemExit('Unauthenticated access did not return 401. Inspect portal routing before treating it as ready.')
            time.sleep(1)
    request=Request('https://'+HOST+'/')
    request.add_unredirected_header('Authorization','Basic '+base64.b64encode((username+':'+password).encode()).decode())
    with opener.open(request,timeout=10) as response:
        if response.status!=200 or b'SHANEATHON' not in response.read():
            raise SystemExit('Authenticated portal validation failed.')
    invalid=Request('https://'+HOST+'/')
    invalid.add_unredirected_header('Authorization','Basic '+base64.b64encode((username+':'+password+'-invalid-check').encode()).decode())
    try:
        with opener.open(invalid,timeout=10):
            raise SystemExit('Invalid credentials were accepted; inspect portal authentication.')
    except HTTPError as error:
        code=error.code;error.close()
        if code!=401: raise SystemExit('Invalid-credential check did not return 401.')
    print('PORTAL READY: https://shaneathon.com')
    print('Unauthenticated HTML/CSS and incorrect password: 401. Correct login: 200. HTTPS verified.')
    print('Password hash stored only in the private server file. Username:',username)
    print('Existing collectors, bots and dashboard access settings unchanged.')


if __name__=='__main__': main()
