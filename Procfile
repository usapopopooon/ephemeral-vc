release: alembic upgrade head
worker: python -m src.main
web: uvicorn src.web.app:app --host 0.0.0.0 --port $PORT
