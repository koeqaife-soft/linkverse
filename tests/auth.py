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
    session: aiohttp.ClientSession
) -> str | None:
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
    session: aiohttp.ClientSession
) -> str | None:
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


async def refresh(token: str, session: aiohttp.ClientSession) -> str | None:
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


async def stress(n: int) -> None:
    session = aiohttp.ClientSession()
    try:
        logging.info("Generating account list")
        accounts = []
        for _ in range(n):
            nickname = generate_random_string(10)
            mail = generate_random_string(12) + "@gmail.com"
            password = generate_random_string(32)
            accounts.append((nickname, mail, password))

        logging.info("Registering accounts...")
        start = time.perf_counter()

        tasks = [asyncio.create_task(register(x[0], x[1], x[2], session))
                 for x in accounts]
        await asyncio.gather(*tasks)

        elapsed = round(time.perf_counter() - start, 5)
        logging.info(f"Registration complete. Time: {elapsed} seconds")

        logging.info("Logging into accounts")
        start = time.perf_counter()

        tasks = [asyncio.create_task(login(x[1], x[2], session))
                 for x in accounts]
        await asyncio.gather(*tasks)

        elapsed = round(time.perf_counter() - start, 5)
        logging.info(f"Login complete. Time: {elapsed} seconds")
    finally:
        await session.close()


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
            n = int(input("Number of accounts> "))
            await stress(n)


if __name__ == "__main__":
    asyncio.run(main())
