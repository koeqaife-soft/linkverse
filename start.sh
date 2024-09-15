#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source .env

if ! systemctl is-active --quiet postgresql; then
    sudo systemctl start postgresql
fi

if [[ $# -gt 0 && $1 =~ ^[0-9]+$ ]]; then
    WORKER_COUNT=$1
elif [[ "$DEBUG" == "True" ]]; then
    WORKER_COUNT=2
else
    WORKER_COUNT=$(nproc)
fi

export _WORKER_COUNT=$WORKER_COUNT
export PYTHONPATH=$SCRIPT_DIR

python -OO init_db.py
hypercorn -w "$WORKER_COUNT" -b 0.0.0.0:6169 api:app --keep-alive 30 --log-level critical
