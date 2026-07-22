FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 2>&1

COPY main.py models.py review.py ./

RUN mkdir -p static/imgs

EXPOSE 8000
CMD ["python", "main.py"]
