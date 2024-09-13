#!/bin/bash

if ! systemctl is-active --quiet postgresql; then
    sudo systemctl start postgresql
fi

hypercorn -w 8 -b 0.0.0.0:6169 api:app
