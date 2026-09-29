"""Empty TCP checks are quiet; malformed HTTP handshakes remain visible."""
import asyncio,os,socket,sys
from pathlib import Path
async def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    child=await asyncio.create_subprocess_exec(sys.executable,'server.py',cwd=Path(__file__).parent,env=dict(os.environ,PORT=str(port),HOST='127.0.0.1'),stderr=asyncio.subprocess.PIPE)
    try:
        for _ in range(30):
            try:reader,writer=await asyncio.open_connection('127.0.0.1',port);break
            except OSError:await asyncio.sleep(.1)
        writer.close();await writer.wait_closed()
        reader,writer=await asyncio.open_connection('127.0.0.1',port)
        writer.write(b'broken request\r\n\r\n');await writer.drain();await reader.read()
        writer.close();await writer.wait_closed()
        child.terminate();_,logs=await child.communicate()
        assert b'stream ends after 0 bytes' not in logs
        assert b'opening handshake failed' in logs and b'broken request' in logs
        print('PASS empty TCP probes filtered; malformed HTTP errors retained')
    finally:
        if child.returncode is None:child.terminate();await child.wait()
asyncio.run(main())
