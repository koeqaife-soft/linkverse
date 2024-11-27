#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd $SCRIPT_DIR

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

source $SCRIPT_DIR/env/bin/activate
python setup.py build_ext --inplace -q
python -OO init_db.py

SSL_ARGS=()
if [[ "$USE_SSL" == "True" ]]; then
    SSL_ARGS+=(--certfile "$CERT_FILE" --keyfile "$KEY_FILE")
fi

python -O -m \
    hypercorn \
    -w "$WORKER_COUNT" \
    -b "$HOST:$PORT" \
    api:app \
    --keep-alive 30 \
    --log-level error \
    -k uvloop \
    "${SSL_ARGS[@]}"
