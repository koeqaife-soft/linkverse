import requests
import mimetypes
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s]: %(message)s')


def get_mime_type(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


def upload_file(file_path: str, file_name: str, token: str) -> None:
    mime_type = get_mime_type(file_path)
    headers = {"Authorization": token}

    response = requests.post(
        "http://localhost:6169/v1/generate_upload_url",
        json={"file_name": file_name},
        headers=headers
    )
    response.raise_for_status()
    data = response.json()
    if not data["success"]:
        logging.error(data)
        exit(1)

    upload_url = data["data"]["upload_url"]
    file_url = data["data"]["file_url"]
    random_file_name = data["data"]["file_name"]

    logging.info("Link is ready!")
    if input("Continue? (y/n): ").strip().lower() != "y":
        print("Operation cancelled.")
        return

    if upload_url:
        with open(file_path, 'rb') as file:
            files = {'file': (file_name, file, mime_type)}
            upload_response = requests.put(upload_url, files=files)

        if upload_response.status_code == 200:
            print(f"File uploaded successfully! File URL: {file_url}")
            print(f"File name: {random_file_name}")
        else:
            print("Failed to upload file.")
            print(f"Response: {upload_response.text}")


def main() -> None:
    file_path = input("Path> ")
    file_name = file_path.split("/")[-1]
    token = input("Token> ").strip()

    upload_file(file_path, file_name, token)


if __name__ == "__main__":
    main()
