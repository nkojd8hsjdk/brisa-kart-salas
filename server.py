"""Brisa Kart v0.21 private-room WebSocket relay. No accounts or saved player data."""
import asyncio, json, os, secrets, time, logging, math, signal
from contextlib import suppress
from http import HTTPStatus
from dataclasses import dataclass, field
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed, InvalidMessage
PROTOCOL=21
ROOMS={}
CLIENTS={}
MAX_ROOMS=int(os.getenv('MAX_ROOMS','100'))
MAX_CONNECTIONS=int(os.getenv('MAX_CONNECTIONS','256'))
ALPHABET='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
class EmptyHealthProbeFilter(logging.Filter):
    """Render's TCP probes close without sending an HTTP request."""
    def filter(self, record):
        error = record.exc_info[1] if record.exc_info else None
        if not isinstance(error, InvalidMessage):
            return True
        cause = error.__cause__
        while cause is not None:
            if isinstance(cause, EOFError) and str(cause) == 'stream ends after 0 bytes, before end of line':
                return False
            cause = cause.__cause__
        return True
@dataclass
class Player:
    ws:object
    slot:int=-1
    room:str=''
    profile:dict=field(default_factory=dict)
    ready:bool=False
    loaded:bool=False
    seen:float=field(default_factory=time.monotonic)
    rate_start:float=field(default_factory=time.monotonic)
    rate_count:int=0
    input_seq:int=-1
@dataclass
class Room:
    code:str
    players:list=field(default_factory=list)
    track:int=0
    phase:str='lobby'
    changed:float=field(default_factory=time.monotonic)
async def send(player,data):
    try:await player.ws.send(json.dumps(data,separators=(',',':'),allow_nan=False))
    except ConnectionClosed:pass
async def broadcast(room,data):
    await asyncio.gather(*(send(p,data) for p in tuple(room.players)))
def integer(value,low,high):
    return isinstance(value,int) and not isinstance(value,bool) and low<=value<=high
def profile(data):
    result={}
    for key,hi in [('pilot',7),('kart',5),('kit',3)]:
        if not integer(data.get(key),0,hi):raise ValueError('Escolha de kart inválida.')
        result[key]=data[key]
    # Friends race on equal equipment. Cosmetic choice is preserved.
    result.update(engine=0,tires=0,handling=0)
    return result
async def lobby(room):
    await broadcast(room,{'type':'lobby','code':room.code,'track':room.track,'phase':room.phase,'members':[{'slot':p.slot,'ready':p.ready,**p.profile} for p in room.players]})
async def leave(p):
    if not p.room:return
    room=ROOMS.pop(p.room,None)
    if room:
        for other in tuple(room.players):
            other.room='';other.slot=-1;other.ready=False;other.loaded=False
            if other is not p:await send(other,{'type':'ended','message':'Seu amigo saiu da sala. Crie outra sala para correr novamente.'})
    p.room='';p.slot=-1
async def handle(p,d):
    kind=d.get('type')
    if kind=='ping':await send(p,{'type':'pong','tick':d.get('tick',0)});return
    if kind=='leave':await leave(p);return
    if kind in ('create','join'):
        if p.room:raise ValueError('Você já está em uma sala.')
        if d.get('protocol')!=PROTOCOL:raise ValueError('Atualizem o jogo para a mesma versão compatível.')
        new_profile=profile(d.get('profile',{}))
        if kind=='create':
            if len(ROOMS)>=MAX_ROOMS:raise ValueError('Servidor cheio. Tente mais tarde.')
            if not integer(d.get('track',0),0,63):raise ValueError('Circuito inválido.')
            code=''.join(secrets.choice(ALPHABET) for _ in range(6))
            while code in ROOMS:code=''.join(secrets.choice(ALPHABET) for _ in range(6))
            room=Room(code,track=d.get('track',0));ROOMS[code]=room
        else:
            code=d.get('code','')
            if not isinstance(code,str) or len(code)!=6:raise ValueError('Use o código de seis caracteres.')
            room=ROOMS.get(code.upper())
            if not room:raise ValueError('Sala não encontrada. Confira o código.')
            if room.phase!='lobby' or len(room.players)>=2:raise ValueError('A sala está cheia ou a corrida já começou.')
        p.slot=len(room.players);p.room=room.code;p.profile=new_profile;p.ready=False;p.loaded=False;p.input_seq=-1
        room.players.append(p);room.changed=time.monotonic()
        await send(p,{'type':'joined','slot':p.slot});await lobby(room);return
    room=ROOMS.get(p.room)
    if not room:raise ValueError('Entre em uma sala primeiro.')
    if kind=='config' and p.slot==0 and room.phase=='lobby':
        if not integer(d.get('track'),0,63):raise ValueError('Circuito inválido.')
        room.track=d['track']
        for member in room.players:member.ready=False
        await lobby(room)
    elif kind=='ready' and room.phase=='lobby':
        p.ready=bool(d.get('ready'));await lobby(room)
    elif kind=='start' and p.slot==0 and room.phase=='lobby':
        if len(room.players)!=2 or not all(x.ready for x in room.players):raise ValueError('Os dois jogadores precisam estar prontos.')
        room.phase='loading';room.changed=time.monotonic()
        await broadcast(room,{'type':'load','track':room.track,'members':[{'slot':x.slot,**x.profile} for x in room.players]})
    elif kind=='loaded' and room.phase=='loading':
        p.loaded=True
        if all(x.loaded for x in room.players):
            room.phase='race';room.changed=time.monotonic();await broadcast(room,{'type':'begin'})
    elif kind=='input' and room.phase=='race' and p.slot==1:
        seq=d.get('seq');value=d.get('input',{})
        if not integer(seq,0,2147483647) or seq<=p.input_seq:return
        if not isinstance(value,dict):raise ValueError('Comando inválido.')
        clean={}
        for key,lo,hi in [('steer',-1,1),('throttle',0,1),('sensitivity',.7,1.3)]:
            v=value.get(key,0 if key!='sensitivity' else 1)
            if not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('Comando inválido.')
            clean[key]=max(lo,min(hi,v))
        for key in ('brake','drift'):clean[key]=bool(value.get(key,False))
        use=d.get('use',0)
        if not integer(use,0,2147483647):raise ValueError('Item inválido.')
        p.input_seq=seq;await send(room.players[0],{'type':'input','seq':seq,'input':clean,'use':use})
    elif kind=='state' and room.phase=='race' and p.slot==0:
        # Physics is host-authoritative. The relay never forwards guest state.
        value=d.get('data')
        if not isinstance(value,dict) or not isinstance(value.get('racers'),list) or len(value['racers'])!=2:raise ValueError('Estado de corrida inválido.')
        await send(room.players[1],{'type':'state','data':value})
    elif kind=='rematch' and p.slot==0 and room.phase=='race':
        room.phase='lobby';room.changed=time.monotonic()
        for x in room.players:x.ready=False;x.loaded=False;x.input_seq=-1
        await lobby(room)
    else:raise ValueError('Ação indisponível nesta sala.')
async def handler(ws):
    if len(CLIENTS)>=MAX_CONNECTIONS:await ws.close(1013,'Servidor cheio');return
    p=Player(ws);CLIENTS[ws]=p
    try:
        async for raw in ws:
            now=time.monotonic();p.seen=now
            if now-p.rate_start>=1:p.rate_start=now;p.rate_count=0
            p.rate_count+=1
            if p.rate_count>100:await ws.close(1008,'Muitas mensagens');break
            try:
                if not isinstance(raw,str):raise ValueError('Mensagem inválida.')
                d=json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Número inválido.')))
                if not isinstance(d,dict):raise ValueError('Mensagem inválida.')
                await handle(p,d)
            except (ValueError,TypeError,KeyError,AttributeError) as err:await send(p,{'type':'error','message':str(err)[:140]})
    except ConnectionClosed:pass
    finally:await leave(p);CLIENTS.pop(ws,None)
async def housekeeping():
    while True:
        await asyncio.sleep(5)
        now=time.monotonic()
        for room in tuple(ROOMS.values()):
            limit=60 if room.phase=='loading' else 1800
            if now-room.changed>limit:
                await broadcast(room,{'type':'ended','message':'A sala expirou. Crie uma nova sala.'})
                if room.players:await leave(room.players[0])
def http_request(connection, request):
    """Serve Render health checks and WebSocket traffic on the assigned port."""
    if request.path == '/health':
        response = connection.respond(HTTPStatus.OK, json.dumps({'status':'ok','protocol':PROTOCOL})+'\n')
        del response.headers['Content-Type']
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
    elif any(value.lower() == 'websocket' for value in request.headers.get_all('Upgrade')):
        return None
    elif request.path == '/':
        response = connection.respond(HTTPStatus.OK,
            'Brisa Kart | AJ Nova Studio\nServidor de salas pronto.\n'
            'No jogo: COM AMIGO > CRIAR SALA. Compartilhe o codigo com seu amigo.\n')
    else:
        response = connection.respond(HTTPStatus.NOT_FOUND, 'Nao encontrado.\n')
    response.headers['Cache-Control'] = 'no-store'
    return response
async def main():
    logging.getLogger('websockets.server').addFilter(EmptyHealthProbeFilter())
    host=os.getenv('HOST','0.0.0.0');port=int(os.getenv('PORT','8765'))
    stop=asyncio.Event()
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        with suppress(NotImplementedError):loop.add_signal_handler(sig,stop.set)
    async with serve(handler,host,port,max_size=32768,max_queue=8,ping_interval=15,ping_timeout=15,compression=None,process_request=http_request,server_header=None):
        logging.warning('Brisa room server listening on %s:%s',host,port)
        cleanup=asyncio.create_task(housekeeping())
        try:
            await stop.wait()
            await asyncio.gather(*(broadcast(room,{'type':'ended','message':'O servidor está reiniciando. Conecte novamente para criar outra sala.'}) for room in tuple(ROOMS.values())))
        finally:
            cleanup.cancel()
            with suppress(asyncio.CancelledError):await cleanup
if __name__=='__main__':asyncio.run(main())
