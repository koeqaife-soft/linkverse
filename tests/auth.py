import time
import aiohttp
import asyncio
import random
import string
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s]: %(message)s')


def generate_random_string(length: int) -> str:
    return ''.join(random.choices(string.ascii_lowercase, k=length))


async def register(
    username: str, email: str, password: str,
    session: aiohttp.ClientSession,
    start_event: asyncio.Event | None = None
) -> str | None:
    if start_event is not None:
        await start_event.wait()
    text = ""
    try:
        async with session.post(
            "http://localhost:6169/v1/auth/register",
            json={
                "username": username,
                "email": email,
                "password": password
            }
        ) as response:
            text = await response.text() or ""
            response.raise_for_status()
            return text
    except aiohttp.ClientResponseError as e:
        logging.error(f"Register failed: {e.status} {e.message}\n{text}")
    except Exception as e:
        logging.error(f"Register failed: {str(e)}\n{text}")
    return None


async def login(
    email: str, password: str,
    session: aiohttp.ClientSession,
    start_event: asyncio.Event | None = None
) -> str | None:
    if start_event is not None:
        await start_event.wait()
    text = ""
    try:
        async with session.post(
            "http://localhost:6169/v1/auth/login",
            json={
                "email": email,
                "password": password
            }
        ) as response:
            text = await response.text() or ""
            response.raise_for_status()
            return text
    except aiohttp.ClientResponseError as e:
        logging.error(f"Login failed: {e.status} {e.message}\n{text}")
    except Exception as e:
        logging.error(f"Login failed: {str(e)}\n{text}")
    return None


async def refresh(
    token: str, session: aiohttp.ClientSession,
    start_event: asyncio.Event | None = None
) -> str | None:
    if start_event is not None:
        await start_event.wait()
    text = ""
    try:
        async with session.post(
            "http://localhost:6169/v1/auth/refresh",
            json={
                "refresh_token": token
            }
        ) as response:
            text = await response.text() or ""
            response.raise_for_status()
            return text
    except aiohttp.ClientResponseError as e:
        logging.error(f"Refresh failed: {e.status} {e.message}\n{text}")
    except Exception as e:
        logging.error(f"Refresh failed: {str(e)}\n{text}")
    return None


async def stress(n: int) -> tuple[float, float]:
    session = aiohttp.ClientSession()
    try:
        logging.debug("Generating account list")
        accounts = []
        for _ in range(n):
            nickname = generate_random_string(10)
            mail = generate_random_string(12) + "@gmail.com"
            password = generate_random_string(32)
            accounts.append((nickname, mail, password))

        logging.debug("Preparing tasks...")
        start_event = asyncio.Event()
        tasks = [
            asyncio.create_task(
                register(x[0], x[1], x[2], session, start_event)
            )
            for x in accounts
        ]

        logging.debug("Registering accounts...")
        start = time.perf_counter()
        start_event.set()
        await asyncio.gather(*tasks)

        elapsed = round(time.perf_counter() - start, 5)
        logging.debug(f"Registration complete. Time: {elapsed} seconds")

        logging.debug("Waiting 1 second")
        await asyncio.sleep(1)

        logging.debug("Preparing login tasks...")
        start_event = asyncio.Event()
        tasks = [
            asyncio.create_task(login(x[1], x[2], session, start_event))
            for x in accounts
        ]

        logging.debug("Logging into accounts...")
        start = time.perf_counter()
        start_event.set()
        await asyncio.gather(*tasks)

        elapsed2 = round(time.perf_counter() - start, 5)
        logging.debug(f"Login complete. Time: {elapsed2} seconds")
    finally:
        await session.close()
    return elapsed, elapsed2


async def main() -> None:
    print(
        "1. Register",
        "2. Login",
        "3. Refresh",
        "4. Stress test",
        sep="\n"
    )
    choice = input("Select test> ")
    match choice:
        case "1":
            username = input("Username> ")
            email = input("Email> ")
            password = input("Password> ")
            async with aiohttp.ClientSession() as session:
                result = await register(username, email, password, session)
            if result:
                print(result)
        case "2":
            email = input("Email> ")
            password = input("Password> ")
            async with aiohttp.ClientSession() as session:
                result = await login(email, password, session)
            if result:
                print(result)
        case "3":
            token = input("Refresh> ")
            async with aiohttp.ClientSession() as session:
                result = await refresh(token, session)
            if result:
                print(result)
        case "4":
            n = int(input("Number of accounts> ") or 5)
            n2 = int(input("Number of tests> ") or 1)
            interval = int(input("Interval> ") or 2)
            register_times = []
            login_times = []
            for i in range(n2):
                logging.info(f"Starting test #{i+1}")
                reg, _login = await stress(n)
                logging.info(f"Register: {reg} s. Login: {_login} s")
                register_times.append(reg)
                login_times.append(_login)
                if i+1 < n2:
                    await asyncio.sleep(interval)

            print()
            if n2 > 1:
                _min = min(*register_times)
                _max = max(*register_times)
                logging.info(f"Register -> Min: {_min} s, Max: {_max} s")

                _min = min(*login_times)
                _max = max(*login_times)
                logging.info(f"Login -> Min: {_min} s, Max: {_max} s")


if __name__ == "__main__":
    asyncio.run(main())
