FROM python:3.11-slim

WORKDIR /app

# Install system deps needed by LightGBM and pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p models

EXPOSE 8000

CMD ["bash", "start.sh"]
