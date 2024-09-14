#!/bin/bash

source .env
sleep 1

if ! systemctl is-active --quiet postgresql; then
    sudo systemctl start postgresql
fi

if [[ "$DEBUG" == "True" ]]; then
    WORKER_COUNT=2
else
    WORKER_COUNT=$(nproc)
fi

python -OO init_db.py
hypercorn -w "$WORKER_COUNT" -b 0.0.0.0:6169 api:app --keep-alive 30 --log-level debug
