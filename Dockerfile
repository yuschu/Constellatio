# Constellatio 应用镜像（Django 5.2 + gunicorn + whitenoise）
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://mirrors.huaweicloud.com/repository/pypi/simple/

WORKDIR /app

# mysqlclient 编译依赖（构建期使用，构建后清理减小镜像）
# apt 源切华为云镜像（deb.debian.org 国内直连不稳定）
RUN sed -i 's|deb.debian.org|mirrors.huaweicloud.com|g; s|security.debian.org|mirrors.huaweicloud.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "./entrypoint.sh"]
