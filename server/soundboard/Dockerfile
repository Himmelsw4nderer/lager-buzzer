FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    mosquitto-clients \
    mpg123 \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

COPY app.py .
COPY requirements.txt .

RUN pip install -r requirements.txt

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
