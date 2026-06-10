FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    mosquito-clients \
    && rm -rf /var/lib/apt/lists/*

COPY app.py .
COPY templates/ ./templates/

RUN pip install flask==3.0.0 paho-mqtt==1.6.1

EXPOSE 5000

CMD ["python3", "app.py"]
