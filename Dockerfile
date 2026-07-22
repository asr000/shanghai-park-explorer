FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libssl-dev libffi-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "echo === Railway Startup === && echo PORT=$PORT && python --version && python -c 'from review import review_image; from models import init_db; print(\"Imports OK\")' && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]