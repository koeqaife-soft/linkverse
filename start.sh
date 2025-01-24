#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd $SCRIPT_DIR

source .env

if ! systemctl is-active --quiet postgresql; then
    sudo systemctl start postgresql
fi

check_redis() {
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1
    return $?
}

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

run_hypercorn() {
    python -O -m hypercorn \
        -w "$1" \
        -b "$HOST:$PORT" \
        api:app \
        --keep-alive 30 \
        --log-level error \
        -k uvloop \
        "${SSL_ARGS[@]}" &
}

run_hypercorn "$WORKER_COUNT"
hypercorn_pid=$!

retry_check_redis() {
    local max_retries=5
    local retries=0
    while ! check_redis; do
        retries=$((retries + 1))
        if [[ "$retries" -ge "$max_retries" ]]; then
            return 1
        fi
        sleep 1
    done
    return 0
}

cleanup() {
    echo 'Shutting down...'
    if [[ -n "$hypercorn_pid" ]]; then
        kill -SIGINT "$hypercorn_pid"
        wait "$hypercorn_pid"
    fi
    exit 0
}
trap cleanup SIGINT

while true; do
    if retry_check_redis; then
        if [[ "$WORKER_COUNT" -ne $_WORKER_COUNT ]]; then
            kill -SIGINT "$hypercorn_pid"
            wait "$hypercorn_pid"
            WORKER_COUNT=$_WORKER_COUNT
            run_hypercorn "$_WORKER_COUNT"
            hypercorn_pid=$!
        fi
    else
        if [[ "$WORKER_COUNT" -ne 1 ]]; then
            kill -SIGINT "$hypercorn_pid"
            wait "$hypercorn_pid"
            WORKER_COUNT=1
            run_hypercorn 1
            hypercorn_pid=$!
        fi

        sleep_interval=1
    fi

    if [[ "$WORKER_COUNT" -eq 1 ]]; then
        sleep_interval=1
    else
        sleep_interval=10
    fi

    sleep "$sleep_interval"
done
