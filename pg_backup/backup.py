import subprocess
import os
import zipfile
import json
import shutil
import datetime

BACKUP_FOLDER = os.path.abspath("backups/")
os.makedirs(BACKUP_FOLDER, exist_ok=True)
TEMP_FILE = os.path.join(BACKUP_FOLDER, "backup.tmp")
TEMP_FILE_ZIP = os.path.join(BACKUP_FOLDER, "backup.tmp.zip")


def dump(user: str, database: str, output_file: str) -> None:
    process = subprocess.run(
        ["pg_dump", "-U", user, "-d", database, "-f", output_file]
    )
    process.check_returncode()


def compress(input_file: str, output_file: str) -> None:
    with zipfile.ZipFile(
        output_file, "w", zipfile.ZIP_LZMA, compresslevel=10
    ) as f:
        f.write(input_file, "backup.sql")


def encrypt_gpg(input_file: str, recipient: str) -> str:
    output_file = input_file + ".gpg"
    subprocess.run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--encrypt",
            "--recipient",
            recipient,
            "--output",
            output_file,
            input_file,
        ],
        check=True,
    )
    return output_file


def cleanup_old_backups(folder: str, keep: int) -> None:
    files = [f for f in os.listdir(folder) if f.endswith(".zip.gpg")]
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
    with open("../config/postgres.json") as f:
        config: dict[str, str] = json.load(f)
    user = config["user"]
    database = config["database"]

    dump(user, database, TEMP_FILE)
    compress(TEMP_FILE, TEMP_FILE_ZIP)

    try:
        with open("recipient.txt", "r") as f:
            gpg_recipient = f.read()
    except FileNotFoundError:
        gpg_recipient = input("GPG RECIPIENT> ")
        with open("recipient.txt", "w") as f:
            f.write(gpg_recipient)
    encrypted_file = encrypt_gpg(TEMP_FILE_ZIP, gpg_recipient)
    os.remove(TEMP_FILE_ZIP)
    os.remove(TEMP_FILE)

    NEW_FILENAME = (
        datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S") +
        ".zip.gpg"
    )
    shutil.move(encrypted_file, os.path.join(BACKUP_FOLDER, NEW_FILENAME))

    cleanup_old_backups(BACKUP_FOLDER, 30)
