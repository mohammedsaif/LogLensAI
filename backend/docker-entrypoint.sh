#!/bin/sh
# Apply database migrations, then start the API. Set SKIP_MIGRATIONS=1 to skip (e.g. when a release job migrates).
set -e
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi
exec "$@"
