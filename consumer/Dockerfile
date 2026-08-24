FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY consumer ./consumer

CMD ["python", "-u", "consumer/main.py"]
