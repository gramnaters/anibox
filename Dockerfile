FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for optional compiled C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
EXPOSE 5000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
