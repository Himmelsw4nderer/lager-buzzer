FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    mosquitto-clients \
    && rm -rf /var/lib/apt/lists/*

COPY timesync_publisher.py .

RUN pip install paho-mqtt==1.6.1

EXPOSE 1883

CMD ["python3", "timesync_publisher.py"]
