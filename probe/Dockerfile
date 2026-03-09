FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir boto3 requests

COPY probe/probe.py /app/probe.py

CMD ["python", "/app/probe.py"]
