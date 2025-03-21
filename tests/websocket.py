import asyncio
import websockets
import ujson


async def async_input(prompt: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, prompt)


async def receive_task(ws: websockets.WebSocketClientProtocol):
    while True:
        response = await ws.recv()
        message = ujson.loads(response)
        print(f"Received: {response}")
        if message["event"] == "please_token":
            token = await async_input("Token: ")
            auth_data = {
                "token": token
            }
            await ws.send(ujson.dumps(auth_data))
            print("Sent auth data!")


async def test_websocket(uri: str):
    try:
        async with websockets.connect(uri) as ws:

            receiver = asyncio.create_task(receive_task(ws))
            await asyncio.gather(receiver)
    except websockets.InvalidStatusCode as e:
        print(f"Connection failed: {e}")
        if e.args:
            print(f"Error details: {e.args[0]}")


uri = "wss://koeqaife.ddns.net:6169/ws"
asyncio.run(test_websocket(uri))
