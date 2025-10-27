from cryptography.fernet import Fernet


def decrypt(input: str, output: str, fernet: Fernet) -> None:
    with open(input, "rb") as f:
        original_data = f.read()

    decrypted_data = fernet.decrypt(original_data)

    with open(output, "wb") as decrypted_file:
        decrypted_file.write(decrypted_data)


if __name__ == "__main__":
    import os
    key = os.path.abspath(input("filekey.key> "))
    input = os.path.abspath(input("Input Filename> "))
    output = os.path.abspath(input("Output Filename> "))
    with open("filekey.key", "rb") as key_file:
        key = key_file.read()

    fernet = Fernet(key)

    decrypt(input, output, fernet)
    print(
        """
::HINT::

psql:
> DROP DATABASE <database>;
> CREATE DATABASE <database>;

bash:
$ psql -U <name> -d <database> -f backup.sql
        """
    )
