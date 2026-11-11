#!/bin/sh
set -e

cd /app/backend
# Um worker: a demo é guiada por um apresentador e o gargalo é Athena/Atlas, não CPU.
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 &
nginx -g 'daemon off;'
