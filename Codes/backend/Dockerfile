FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic
ENV WASL_ENV_FILE=/dev/null PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
