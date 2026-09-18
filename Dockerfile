# ---------- 阶段一：构建前端 ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段二：后端运行时 ----------
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# 前端构建产物由 FastAPI 托管（main.py 中的 static 挂载）
COPY --from=frontend /build/dist ./static

# 非 root 运行，SQLite 数据目录可挂载持久化
RUN useradd -r -u 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
