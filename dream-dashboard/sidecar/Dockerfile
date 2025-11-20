FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests==2.32.3
COPY sidecar.py /app/sidecar.py
CMD ["python", "/app/sidecar.py"]
