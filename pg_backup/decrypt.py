print("""
>> GPG <<

!! Get the file on the main pc

bash (main pc):
$ gpg --output backup.zip --decrypt <date>.zip.gpg

!! Move backup.zip to server for next actions

psql:
> DROP DATABASE <database>;
> CREATE DATABASE <database>;

bash:
$ psql -U <name> -d <database> -f backup.sql
""")
