import os


def generate_key(length: int = 32) -> str:
    return os.urandom(length).hex()


secret_key = generate_key()
refresh_secret_key = generate_key()

print(f'SECRET_KEY="{secret_key}"')
print(f'SECRET_REFRESH_KEY="{refresh_secret_key}"')
