#!/bin/sh
set -euo pipefail

python scripts/wait_for_db.py
alembic upgrade head

exec "$@"
