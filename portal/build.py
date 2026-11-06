"""Generate static portal files. Authentication is required at Nginx, not here."""
import argparse
from html import escape
import json
from pathlib import Path
from urllib.parse import urlsplit


def render(links):
    cards=[]
    for item in links:
        address=urlsplit(item['url'])
        if address.scheme!='https' or not address.hostname or address.username or address.password:
            raise ValueError('Portal links require HTTPS without embedded credentials')
        cards.append('<a class="card" href="'+escape(item['url'],quote=True)+'" target="_blank" rel="noopener noreferrer">'
            '<span class="category">'+escape(item['category'])+'</span><span class="name">'+escape(item['name'])+
            '<span aria-hidden="true">↗</span></span><span class="description">'+escape(item['description'])+'</span></a>')
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive"><title>Shaneathon · Portal</title>
<link rel="stylesheet" href="/portal.css"></head><body><main>
<header><p class="eyebrow">SHANEATHON</p><h1>Your workspace.</h1><p class="intro">Markets, paper portfolios and research, together.</p></header>
<nav aria-label="Project links" class="grid">'''+''.join(cards)+'''</nav>
<footer>Shaneathon · Personal workspace</footer></main></body></html>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--links',type=Path,default=Path(__file__).with_name('links.json'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    html=render(json.loads(args.links.read_text()))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'index.html').write_text(html)
    (args.out/'portal.css').write_text(Path(__file__).with_name('portal.css').read_text())
    print('Static portal prepared. Publication requires server-side authentication.')


if __name__=='__main__': main()
