"""Check the hosting entry point locally, including PORT and graceful shutdown."""
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import sys
import urllib.error
import urllib.request
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parent

def http(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode()

async def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, HOST='127.0.0.1', PORT=str(port))
    base = f'http://127.0.0.1:{port}'
    url = f'ws://127.0.0.1:{port}'
    server = await asyncio.create_subprocess_exec(sys.executable, 'server.py', cwd=ROOT, env=env)
    try:
        for _ in range(50):
            try:
                status, headers, body = await asyncio.to_thread(http, base+'/health')
                break
            except OSError:
                await asyncio.sleep(.1)
        else:
            raise AssertionError('Server did not start on assigned PORT')
        assert status == 200
        assert json.loads(body) == {'status':'ok', 'protocol':21}
        assert headers['Content-Type'].startswith('application/json')
        assert headers['Cache-Control'] == 'no-store'
        assert (await asyncio.to_thread(http, base+'/'))[0] == 200
        assert (await asyncio.to_thread(http, base+'/missing'))[0] == 404
        protocol = await asyncio.create_subprocess_exec(sys.executable, 'test_server.py',
            cwd=ROOT, env=dict(env, BRISA_SERVER_URL=url))
        assert await asyncio.wait_for(protocol.wait(), 30) == 0
        async with connect(url, proxy=None) as player:
            await player.send(json.dumps({'type':'create', 'protocol':21,
                'profile':{'pilot':0,'kart':0,'kit':0}, 'track':63}))
            assert json.loads(await player.recv())['type'] == 'joined'
            room = json.loads(await player.recv())
            status, _, body = await asyncio.to_thread(http, base+'/health')
            assert status == 200 and room['code'] not in body
            await player.send('{"type":"ping","tick":123}')
            assert json.loads(await player.recv()) == {'type':'pong','tick':123}
            server.send_signal(signal.SIGTERM)
            assert json.loads(await asyncio.wait_for(player.recv(), 5))['type'] == 'ended'
            await asyncio.wait_for(player.wait_closed(), 5)
            assert player.close_code == 1001
        assert await asyncio.wait_for(server.wait(), 5) == 0
        print('PASS assigned PORT, HTTP health/root/404, concurrent HTTP and WebSocket, protocol 21, SIGTERM notification and close 1001')
    finally:
        if server.returncode is None:
            server.terminate()
            await asyncio.wait_for(server.wait(), 5)

if __name__ == '__main__':
    asyncio.run(main())
