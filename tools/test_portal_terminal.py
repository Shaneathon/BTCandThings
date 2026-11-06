"""Exercise hidden portal credentials in a real controlling pseudo-terminal."""
import errno
import os
from pathlib import Path
import pty
import select
import signal
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'portal'))
from install import read_credentials


class PortalTerminalTests(unittest.TestCase):
    def exercise(self,confirmation,expected):
        password='fixture-only-password-123'
        pid,fd=pty.fork()
        if pid==0:
            try:
                user,secret=read_credentials()
                code=0 if user=='shane' and secret==password else 3
            except SystemExit:
                code=2
            except BaseException:
                code=4
            os._exit(code)
        output=b''
        prompts=[(b'Portal username [shane]: ',b'\n'),
                 (b'Portal password (hidden; at least 12 characters): ',password.encode()+b'\n'),
                 (b'Repeat portal password: ',confirmation.encode()+b'\n')]
        deadline=time.monotonic()+10
        status=None
        try:
            while time.monotonic()<deadline:
                if select.select([fd],[],[],.1)[0]:
                    try: chunk=os.read(fd,4096)
                    except OSError as error:
                        if error.errno==errno.EIO: chunk=b''
                        else: raise
                    output+=chunk
                if prompts and prompts[0][0] in output:
                    _,answer=prompts.pop(0)
                    os.write(fd,answer)
                done,result=os.waitpid(pid,os.WNOHANG)
                if done:
                    status=result
                    break
            self.assertIsNotNone(status,'Credential prompt stalled')
            self.assertEqual(os.waitstatus_to_exitcode(status),expected)
            self.assertNotIn(password.encode(),output,'Password was echoed')
        finally:
            os.close(fd)
            if status is None:
                os.kill(pid,signal.SIGKILL)
                os.waitpid(pid,0)

    def test_matching_password_hidden_in_nonseekable_terminal(self):
        self.exercise('fixture-only-password-123',0)

    def test_mismatch_rejected_without_echo(self):
        self.exercise('different-fixture-value',2)
