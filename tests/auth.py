import time
import aiohttp
import asyncio
import random
import string
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s]: %(message)s')


def generate_random_string(length: int) -> str:
    return ''.join(random.choices(string.ascii_lowercase, k=length))


async def register(username: str, email: str, password: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:6169/v1/auth/register",
                json={
                    "username": username,
                    "email": email,
                    "password": password
                }
            ) as response:
                response.raise_for_status()
                return await response.text()
    except aiohttp.ClientResponseError as e:
        logging.error(f"Register failed: {e.status} {e.message}")
    except Exception as e:
        logging.error(f"Register failed: {str(e)}")
    return None


async def login(email: str, password: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:6169/v1/auth/login",
                json={
                    "email": email,
                    "password": password
                }
            ) as response:
                response.raise_for_status()
                return await response.text()
    except aiohttp.ClientResponseError as e:
        logging.error(f"Login failed: {e.status} {e.message}")
    except Exception as e:
        logging.error(f"Login failed: {str(e)}")
    return None


async def refresh(token: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:6169/v1/auth/refresh",
                json={
                    "refresh_token": token
                }
            ) as response:
                response.raise_for_status()
                return await response.text()
    except aiohttp.ClientResponseError as e:
        logging.error(f"Refresh failed: {e.status} {e.message}")
    except Exception as e:
        logging.error(f"Refresh failed: {str(e)}")
    return None


async def stress() -> None:
    n = int(input("Number of accounts> "))
    logging.info("Generating account list")
    accounts = []
    for _ in range(n):
        nickname = generate_random_string(10)
        mail = generate_random_string(12) + "@gmail.com"
        password = generate_random_string(32)
        accounts.append((nickname, mail, password))

    logging.info("Registering accounts...")
    start = time.perf_counter()

    tasks = [asyncio.create_task(register(x[0], x[1], x[2])) for x in accounts]
    await asyncio.gather(*tasks)

    elapsed = round(time.perf_counter() - start, 5)
    logging.info(f"Registration complete. Time: {elapsed} seconds")

    logging.info("Logging into accounts")
    start = time.perf_counter()

    tasks = [asyncio.create_task(login(x[1], x[2])) for x in accounts]
    await asyncio.gather(*tasks)

    elapsed = round(time.perf_counter() - start, 5)
    logging.info(f"Login complete. Time: {elapsed} seconds")


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

            result = await register(username, email, password)
            if result:
                print(result)
        case "2":
            email = input("Email> ")
            password = input("Password> ")

            result = await login(email, password)
            if result:
                print(result)
        case "3":
            token = input("Refresh> ")

            result = await refresh(token)
            if result:
                print(result)
        case "4":
            await stress()


if __name__ == "__main__":
    asyncio.run(main())
