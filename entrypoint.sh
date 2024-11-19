#!/bin/sh

alembic upgrade head

python /app/app.py