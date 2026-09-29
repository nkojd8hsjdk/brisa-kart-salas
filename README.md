# Brisa Kart — servidor de salas

Servidor WebSocket de duas pessoas para o jogo Android da AJ Nova Studio.
O celular anfitrião simula a corrida; o servidor encaminha os dados entre as redes.

## Executar

```sh
python -m pip install -r requirements.txt
python server.py
```

Python 3.12. Porta padrão 8765; em hospedagem, usa `PORT` e escuta em `0.0.0.0`.
`GET /health` retorna o estado do serviço e a versão do protocolo, sem revelar salas.

## Render

Plano de testes gratuito, uma instância, região Virginia.
Build: `pip install -r requirements.txt`. Start: `python server.py`.
`render.yaml` contém a configuração equivalente para Blueprint.

As salas são mantidas em memória. Reinícios encerram as partidas; não use múltiplas instâncias.
O plano gratuito pode suspender o serviço ocioso, então o cliente precisa tratar a espera inicial.

## Testar

`python test_hosting.py` testa HTTP, WebSocket, salas e encerramento controlado localmente.
`BRISA_SERVER_URL=wss://ENDERECO-REAL python test_server.py` testa o servidor publicado.

Este repositório contém somente o servidor. O projeto do jogo e a assinatura Android ficam separados.
