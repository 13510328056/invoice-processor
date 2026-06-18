# ────────────────────────────────────────────
# 发票信息识别服务 — 多阶段 Docker 构建
# ────────────────────────────────────────────
# PaddleOCR 依赖 OpenCV，需要系统级图形库。

FROM python:3.11-slim AS builder

WORKDIR /build

# 安装构建依赖（编译 C 扩展需要 build-essential 和 python3-dev）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0t64 \
    build-essential \
    python3-dev \
    -o Acquire::Retries=3 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY invoice_processor.py .

# 安装 Python 依赖（缓存层）
RUN pip install --no-cache-dir -e .


# ── 运行时 ──
FROM python:3.11-slim

WORKDIR /app

# 运行时系统依赖（OpenCV + 字体）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0t64 \
    fonts-noto-cjk \
    -o Acquire::Retries=3 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制安装的包
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# 复制应用代码
COPY pyproject.toml .
COPY src/ src/
COPY web_api/ web_api/
COPY invoice_processor.py .
COPY config.yaml .
COPY web_config.yaml .

# 创建临时文件目录
RUN mkdir -p /tmp/invoice_processor_web

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

EXPOSE 8000

# 单 worker 模式（PaddleOCR 每个进程 ~1-2GB 内存）
CMD ["uvicorn", "web_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
