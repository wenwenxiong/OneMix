# OneMix 统一镜像定义：Compose 通过 build.target 分别构建 api / web
# -----------------------------------------------------------------------------
# target: api — FastAPI + Uvicorn
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS api

WORKDIR /app

# 不在镜像构建阶段执行 apt-get：国内/受限网络常无法访问 deb.debian.org。
# Pillow 等对 Linux amd64 通常提供 manylinux 预编译 wheel。

# 根目录 requirements.txt 含 `-r backend/requirements.txt`，pip 解析前须已存在该路径
COPY requirements.txt /app/requirements.txt
COPY backend/requirements.txt /app/backend/requirements.txt

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir \
        --index-url "${PIP_INDEX_URL}" \
        --timeout 120 \
        --retries 10 \
        -r /app/requirements.txt

COPY backend/ /app/

ENV PYTHONUNBUFFERED=1
ENV ONEMIX_DATA_DIR=/data/onemix
ENV HOME=/data

EXPOSE 8767

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8767"]

# -----------------------------------------------------------------------------
# target: web-builder — 在镜像内编译前端（Vite 产物 /build/dist）
# -----------------------------------------------------------------------------
FROM node:20-alpine AS web-builder

WORKDIR /build

# 默认使用国内 npm 镜像，海外构建可通过 --build-arg NPM_REGISTRY 覆盖
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry "${NPM_REGISTRY}"

# 先复制依赖清单以利用 layer 缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# 再复制源码并构建
COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# target: web — Nginx 托管前端构建产物，并反代 /api、/health 到 api
# -----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS web

COPY --from=web-builder /build/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
