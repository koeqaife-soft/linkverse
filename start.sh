#!/bin/bash

if ! systemctl is-active --quiet postgresql; then
    sudo systemctl start postgresql
fi

gunicorn -w 8 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:6169 api:app
