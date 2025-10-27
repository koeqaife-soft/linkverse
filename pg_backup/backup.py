import subprocess
import os
import zipfile
import json
import shutil
from cryptography.fernet import Fernet

BACKUP_FOLDER = os.path.abspath("backups/")
os.makedirs(BACKUP_FOLDER, exist_ok=True)
TEMP_FILE = os.path.join(BACKUP_FOLDER, "backup.tmp")
TEMP_FILE_ZIP = os.path.join(BACKUP_FOLDER, "backup.tmp.zip")

with open("filekey.key", "rb") as key_file:
    key = key_file.read()

fernet = Fernet(key)


def dump(
    user: str,
    database: str,
    password: str,
    output_file: str
) -> None:
    os.environ["PGPASSWORD"] = password
    process = subprocess.run([
        "pg_dump",
        "-U", user,
        "-d", database,
        "-f", output_file
    ])
    process.check_returncode()


def compress(input_file: str, output_file: str) -> None:
    with zipfile.ZipFile(
        output_file, "w",
        zipfile.ZIP_LZMA, compresslevel=10
    ) as f:
        f.write(input_file, "backup.sql")


def encrypt(file: str) -> None:
    with open(file, "rb") as f:
        original_data = f.read()

    encrypted_data = fernet.encrypt(original_data)

    with open(file, "wb") as encrypted_file:
        encrypted_file.write(encrypted_data)


def cleanup_old_backups(folder: str, keep: int) -> None:
    files = [
        f for f in os.listdir(folder)
        if f.endswith(".zip")
    ]
    if len(files) <= keep:
        return

    files.sort(reverse=True)

    to_delete = files[keep:]

    for filename in to_delete:
        path = os.path.join(folder, filename)
        try:
            os.remove(path)
            print(f"Deleted old backup: {filename}")
        except OSError as e:
            print(f"Failed to delete {filename}: {e}")


if __name__ == "__main__":
    import datetime
    with open("../config/postgres.json") as f:
        config: dict[str, str] = json.load(f)
    user = config["user"]
    database = config["database"]
    password = config["password"]

    dump(user, database, password, TEMP_FILE)
    compress(TEMP_FILE, TEMP_FILE_ZIP)
    encrypt(TEMP_FILE_ZIP)

    NEW_FILENAME = (
        datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S") +
        ".zip"
    )
    shutil.move(
        TEMP_FILE_ZIP,
        os.path.join(BACKUP_FOLDER, NEW_FILENAME)
    )
    os.remove(TEMP_FILE)
    cleanup_old_backups(BACKUP_FOLDER, 30)
