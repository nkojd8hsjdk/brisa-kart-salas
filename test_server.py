import asyncio,json,sys,os
from websockets.asyncio.client import connect
URL=os.getenv('BRISA_SERVER_URL','ws://127.0.0.1:8765')
async def receive(ws,kind):
 for _ in range(30):
  data=json.loads(await asyncio.wait_for(ws.recv(),3))
  if data['type']==kind:return data
 raise AssertionError(kind)
async def send(ws,kind,**kw):await ws.send(json.dumps({'type':kind,**kw}))
async def main():
 async with connect(URL,proxy=None) as a,connect(URL,proxy=None) as b,connect(URL,proxy=None) as c:
  p={'pilot':0,'kart':0,'kit':0}
  await send(a,'create',protocol=20,profile=p);assert 'versão' in (await receive(a,'error'))['message']
  await send(a,'create',protocol=21,profile=p,track=0);assert (await receive(a,'joined'))['slot']==0
  room=await receive(a,'lobby');code=room['code'];assert len(code)==6
  await send(b,'join',protocol=21,profile={'pilot':7,'kart':5,'kit':3},code=code)
  assert (await receive(b,'joined'))['slot']==1
  room=await receive(b,'lobby');assert len(room['members'])==2
  await receive(a,'lobby')
  await send(c,'join',protocol=21,profile=p,code=code);assert 'cheia' in (await receive(c,'error'))['message']
  await send(b,'config',track=5);await receive(b,'error')
  await send(a,'start');await receive(a,'error')
  for ws in (a,b):
   await send(ws,'ready',ready=True)
   await receive(a,'lobby');await receive(b,'lobby')
  await send(a,'start');await receive(a,'load');await receive(b,'load')
  await send(a,'loaded');await send(b,'loaded');await receive(a,'begin');await receive(b,'begin')
  await send(b,'input',seq=1,input={'steer':10,'throttle':2,'brake':False,'drift':True},use=3)
  cmd=await receive(a,'input');assert cmd['input']['steer']==1 and cmd['input']['throttle']==1 and cmd['use']==3
  await send(b,'state',data={'racers':[{},{}]});await receive(b,'error')
  await send(a,'state',data={'racers':[{'s':4},{'s':2}],'state':'race'})
  assert (await receive(b,'state'))['data']['racers'][0]['s']==4
  await send(a,'rematch');assert (await receive(a,'lobby'))['phase']=='lobby';await receive(b,'lobby')
  await send(b,'leave');assert (await receive(a,'ended'))['type']=='ended'
 print('PASS room protocol, version, capacity, readiness, authority, bounded input, state relay, rematch, disconnection')
asyncio.run(main())
