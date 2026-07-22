FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn

COPY main_simple.py .

CMD ["python", "main_simple.py"]