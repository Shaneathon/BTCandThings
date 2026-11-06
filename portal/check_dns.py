"""Read-only system versus authoritative DNS diagnostic; standard library only."""
import ipaddress
import secrets
import socket
import struct

HOST='shaneathon.com'


def skip_name(packet,offset):
    for _ in range(128):
        size=packet[offset]
        if size & 0xc0 == 0xc0: return offset+2
        offset+=1
        if size==0: return offset
        offset+=size
    raise ValueError('Invalid DNS name')


def query(server,kind):
    address=socket.getaddrinfo(server,53,family=socket.AF_INET,type=socket.SOCK_DGRAM)[0][4]
    identifier=secrets.randbelow(65536)
    question=b''.join(bytes([len(label)])+label.encode() for label in HOST.split('.'))+b'\x00'
    packet=struct.pack('!6H',identifier,0,1,0,0,0)+question+struct.pack('!2H',kind,1)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.connect(address)
        sock.send(packet)
        reply=sock.recv(65535)
    ident,flags,questions,answers,_,_=struct.unpack_from('!6H',reply)
    if ident!=identifier or not flags & 0x8000 or flags & 0x0200: raise ValueError('Invalid or truncated DNS response')
    offset=12
    for _ in range(questions): offset=skip_name(reply,offset)+4
    values=[]
    for _ in range(answers):
        offset=skip_name(reply,offset)
        record_type,record_class,ttl,length=struct.unpack_from('!HHIH',reply,offset)
        offset+=10
        value=reply[offset:offset+length]
        offset+=length
        if record_class==1 and record_type in (1,28):
            values.append(dict(address=str(ipaddress.ip_address(value)),ttl_seconds=ttl))
    return dict(authoritative=bool(flags & 0x0400),rcode=flags & 15,answers=values)


if __name__=='__main__':
    print('Expected droplet IPv4: 165.22.162.116')
    try:
        print('System resolver:',sorted({r[4][0] for r in socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM)}))
    except OSError as error: print('System resolver:',type(error).__name__)
    for server in ('nsa1.squarespacedns.com','nsa2.squarespacedns.com'):
        for name,kind in [('A',1),('AAAA',28)]:
            try: print(server,name,query(server,kind))
            except (OSError,ValueError,IndexError,struct.error) as error:
                print(server,name,type(error).__name__)
