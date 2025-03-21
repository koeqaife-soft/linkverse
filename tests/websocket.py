import asyncio
import websockets
import ujson

TOKEN = input("TOKEN: ")


async def receive_task(ws: websockets.WebSocketClientProtocol):
    while True:
        response = await ws.recv()
        print(f"Received: {response}")


async def test_websocket(uri: str):
    try:
        async with websockets.connect(uri) as ws:
            auth_data = {
                "token": TOKEN
            }
            await ws.send(ujson.dumps(auth_data))
            receiver = asyncio.create_task(receive_task(ws))
            await asyncio.gather(receiver)
    except websockets.InvalidStatusCode as e:
        print(f"Connection failed: {e}")
        if e.args:
            print(f"Error details: {e.args[0]}")


uri = "wss://koeqaife.ddns.net:6169/ws"
asyncio.run(test_websocket(uri))
