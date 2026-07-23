FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
RUN pip install --no-cache-dir "fast-flights>=3.0" "mcp[cli]>=1.0.0" "airportsdata>=20240101"
CMD ["python", "server.py"]
