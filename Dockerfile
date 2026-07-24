FROM python:3.11-slim

RUN apt-get update && apt-get install -y wget gnupg unzip curl ca-certificates \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV CHROME_BIN=/usr/bin/google-chrome

EXPOSE 10000
CMD ["gunicorn", "-b", "0.0.0.0:10000", "--workers", "1", "--timeout", "600", "app:app"]