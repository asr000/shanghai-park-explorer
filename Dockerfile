FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py models.py review.py ./

RUN mkdir -p static/imgs

EXPOSE 8080

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips "*"
