import asyncio,json,os
from websockets.asyncio.client import connect
URL=os.getenv('BRISA_SERVER_URL','ws://127.0.0.1:8765')
async def recv(ws,kind):
 for _ in range(40):
  d=json.loads(await asyncio.wait_for(ws.recv(),8))
  if d['type']==kind:return d
 raise AssertionError(kind)
async def send(ws,t,**kw):await ws.send(json.dumps(dict(type=t,**kw)))
async def main():
 async with connect(URL,proxy=True if URL.startswith('wss') else None) as a,connect(URL,proxy=True if URL.startswith('wss') else None) as b:
  profile={'pilot':8,'kart':1,'kit':0}
  await send(a,'create',protocol=27,profile=profile,track=0,difficulty=3);await recv(a,'error')
  await send(a,'create',protocol=27,profile=profile,track=0,difficulty=2);await recv(a,'joined');lobby=await recv(a,'lobby');code=lobby['code'];assert lobby['difficulty']==2 and len(lobby['bots'])==2
  await send(b,'join',protocol=24,profile=profile,code=code);await recv(b,'error')
  await send(b,'join',protocol=27,profile={'pilot':9,'kart':5,'kit':3},code=code);await recv(b,'joined');lobby=await recv(b,'lobby');await recv(a,'lobby')
  assert len(lobby['members'])==2 and len(lobby['bots'])==2
  assert len(set([8,9]+[p['pilot'] for p in lobby['bots']]))==4
  await send(b,'config',track=3,difficulty=0);await recv(b,'error')
  for level in [0,1,2]:
   for w in (a,b):
    await send(w,'ready',ready=True);await recv(a,'lobby');await recv(b,'lobby')
   await send(a,'config',track=63-level,difficulty=level)
   lobby=await recv(a,'lobby');guest=await recv(b,'lobby')
   assert lobby==guest and lobby['difficulty']==level and not any(p['ready'] for p in lobby['members'])
   await send(a,'start');await recv(a,'error')
   await send(a,'config',track=0,difficulty=True);await recv(a,'error')
   for w in (a,b):
    await send(w,'ready',ready=True);await recv(a,'lobby');await recv(b,'lobby')
   await send(a,'start');load=await recv(a,'load');assert load==await recv(b,'load')
   assert load['difficulty']==level and len(load['bots'])==2
   await send(a,'loaded');await send(b,'loaded');await recv(a,'begin');await recv(b,'begin')
   await send(b,'state',data={'racers':[{}, {}, {}, {}]});await recv(b,'error')
   await send(a,'state',data={'racers':[{}, {}]});await recv(a,'error')
   sample={'racers':[{'s':i*10} for i in range(4)],'state':'race'}
   await send(a,'state',data=sample);assert (await recv(b,'state'))['data']==sample
   await send(a,'rematch');lobby=await recv(a,'lobby');await recv(b,'lobby');assert lobby['difficulty']==level
  await send(b,'leave');await recv(a,'ended')
 print('PASS v27: 4 racers, 2 bots, 3 difficulties, permission checks, config resets ready, same load, rematch, incompatible protocol rejected')
if __name__=='__main__':asyncio.run(main())
