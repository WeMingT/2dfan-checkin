FROM python:3.13-slim

WORKDIR /app

# 安装 Chromium 及其依赖
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 设置 Chromium 环境变量
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMIUM_FLAGS="--no-sandbox --headless --disable-gpu --disable-dev-shm-usage"

ADD requirements.txt /app/requirements.txt

RUN python -m pip install -r requirements.txt

ADD . .

# 默认使用浏览器模式
ENV CHECKIN_MODE=browser

ENTRYPOINT ["python", "main.py"]
