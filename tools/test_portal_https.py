"""Real loopback TLS: local portal routing must retain certificate validation."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'portal'))
from install import HOST, LocalHTTPSConnection, LocalHTTPSHandler, NoRedirect


class PortalHTTPSTests(unittest.TestCase):
    def test_local_validation_checks_real_host_and_trusted_certificate(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'portal-test')
            def log_message(self,*args): pass
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);cert=root/'cert.pem';key=root/'key.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                            '-subj','/CN='+HOST,'-addext','subjectAltName=DNS:'+HOST,
                            '-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert,key)
            server.socket=context.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            connect=socket.create_connection
            observed=[]
            def redirect(address,*args,**kwargs):
                observed.append(address)
                return connect(('127.0.0.1',server.server_port),*args,**kwargs)
            try:
                trusted=ssl.create_default_context(cafile=str(cert))
                self.assertTrue(trusted.check_hostname)
                with patch('install.socket.create_connection',side_effect=redirect):
                    opener=build_opener(ProxyHandler({}),NoRedirect(),LocalHTTPSHandler(context=trusted))
                    with opener.open('https://'+HOST+'/',timeout=3) as response:
                        self.assertEqual(response.read(),b'portal-test')
                    # The same server certificate must be rejected without trust.
                    untrusted=build_opener(ProxyHandler({}),NoRedirect(),LocalHTTPSHandler())
                    with self.assertRaises(URLError): untrusted.open('https://'+HOST+'/',timeout=3)
                self.assertTrue(all(address==('127.0.0.1',443) for address in observed))
                with self.assertRaises(ValueError): LocalHTTPSConnection('other.example').connect()
            finally:
                server.shutdown();server.server_close();thread.join()
