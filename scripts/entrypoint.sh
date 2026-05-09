#!/bin/bash
set -e

echo "Waiting for database to be ready..."
while ! python -c "
import asyncio, asyncpg, os
async def check():
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'db'),
        port=int(os.getenv('DB_PORT', '5432')),
        user=os.getenv('DB_USER', 'ai_parking'),
        password=os.getenv('DB_PASSWORD', 'ai_parking_pass'),
        database=os.getenv('DB_NAME', 'ai_parking_central'),
    )
    await conn.close()
asyncio.run(check())
" 2>/dev/null; do
    echo "DB not ready, retrying in 2s..."
    sleep 2
done
echo "Database is ready!"

# Auto-generate migration if no versions exist
if [ -z "$(ls -A alembic/versions/*.py 2>/dev/null)" ]; then
    echo "No migrations found. Generating initial migration..."
    alembic revision --autogenerate -m "initial schema"
fi

echo "Running database migrations..."
alembic upgrade head

echo "Seeding initial data..."
python -m scripts.seed

echo "Seeding Gujarat data..."
python -m scripts.seed_gujarat

echo "Starting application..."
exec uvicorn src.app.main:app --host 0.0.0.0 --port 8000 --reload
