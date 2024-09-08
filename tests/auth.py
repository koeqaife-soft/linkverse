import requests

username = input("Username> ")
email = input("Email> ")
password = input("Password> ")

response = requests.post(
    "http://localhost:6169/v1/auth/register",
    json={
        "username": username,
        "email": email,
        "password": password
    }
)

print(response.text)

email = input("Email> ")
password = input("Password> ")

response = requests.post(
    "http://localhost:6169/v1/auth/login",
    json={
        "email": email,
        "password": password
    }
)

print(response.text)
