FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py models.py review.py ./

# Create static storage directory
RUN mkdir -p static/imgs

# Railway provides PORT env var
EXPOSE 8000

CMD ["python", "main.py"]