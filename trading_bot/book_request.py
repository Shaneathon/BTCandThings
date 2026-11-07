"""Public book request construction; cache policy never relaxes freshness checks."""
from urllib.parse import quote,urlencode
from urllib.request import Request
import uuid


def request(contract, *, bypass=True):
    url='https://gateway.polymarket.us/v1/markets/'+quote(contract,safe='')+'/book'
    if bypass:
        # The deployment probe must establish that this query reaches a fresh
        # provider snapshot. Unknown/ignored query parameters are NOT approval.
        url+='?'+urlencode({'_shaneathon_snapshot':uuid.uuid4().hex})
    return Request(url,headers={'User-Agent':'Shaneathon-ObservedPaper/1.0',
                                'Cache-Control':'no-cache','Pragma':'no-cache'},method='GET')
