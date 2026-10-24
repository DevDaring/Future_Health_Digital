#!/usr/bin/env bash
# Stop only the WASL API (matches its module and port).
PORT="${PORT:-8200}"
for p in $(ps -eo pid,args | awk -v port="--port $PORT" '/uvicorn app.main:app/ && index($0, port) && !/awk/ {print $1}'); do kill "$p"; done
