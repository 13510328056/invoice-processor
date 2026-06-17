# 发票识别服务 — 部署指南

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux (推荐 Ubuntu 22.04+) / Windows / macOS |
| Docker Engine | 24.0+ |
| Docker Compose | v2.0+ |
| 内存 | ≥ 4GB（PaddleOCR 占用 1~2GB） |
| 磁盘 | ≥ 10GB（含 PaddleOCR 模型） |
| CPU | 推荐 4 核以上 |

---

## 一、快速部署（Docker Compose）

### 1. 准备

```bash
# 克隆仓库
git clone https://github.com/13510328056/invoice-processor.git
cd invoice-processor
```

### 2. 按需修改配置

编辑 `web_config.yaml` 调整 Web 服务参数：

```yaml
web:
  port: 8000                      # 对外端口
  max_upload_size_mb: 100         # 单文件上传限制
  pre_warm_ocr: true              # 启动时预热 PaddleOCR
  cors_origins:
    - "*"                         # 生产环境请替换为具体域名
```

编辑 `config.yaml` 调整 OCR 和处理参数：

```yaml
ocr:
  engine: paddleocr
  use_gpu: false                  # 有 GPU 可改为 true
processing:
  max_workers: 4                  # 并发线程数
```

### 3. 构建并启动

```bash
# 首次构建并后台启动
docker compose up -d

# 查看启动日志
docker compose logs -f

# 等待服务就绪（首次需下载 PaddleOCR 模型，约 30~60 秒）
curl http://localhost:8000/api/v1/health
```

预期返回：
```json
{"status":"ok","version":"1.0.0","uptime_seconds":12.34,"ocr_loaded":true}
```

### 4. 验证

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 测试单文件识别
curl -X POST http://localhost:8000/api/v1/extract \
  -F "file=@测试发票.pdf"

# 访问 API 文档
# 浏览器打开 http://localhost:8000/docs
```

---

## 二、生产环境部署

### 推荐架构

```
客户端（浏览器/App）
        │
        ▼
   Nginx（HTTPS + 反向代理 + 限流）
        │
        ▼
   发票识别服务（Docker）
        │
        ▼
   PaddleOCR + 处理管线
```

### Nginx 反向代理配置

```nginx
server {
    listen 443 ssl http2;
    server_name invoice-api.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # 文件上传大小限制
    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 长连接超时（OCR 处理耗时较长）
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}

server {
    listen 80;
    server_name invoice-api.example.com;
    return 301 https://$server_name$request_uri;
}
```

### docker-compose.prod.yml

```yaml
services:
  invoice-processor-api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: invoice-processor
    ports:
      - "127.0.0.1:8000:8000"   # 仅本地监听，通过 Nginx 转发
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./web_config.yaml:/app/web_config.yaml:ro
      - invoice_temp:/tmp/invoice_processor_web
    environment:
      - INVOICE_WEB_MAX_UPLOAD_SIZE_MB=100
      - INVOICE_WEB_PRE_WARM_OCR=true
      - INVOICE_WEB_CORS_ORIGINS=https://invoice-app.example.com
      - INVOICE_WEB_LOG_LEVEL=INFO
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 4g
        reservations:
          memory: 2g
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  invoice_temp:
```

启动生产环境：

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## 三、配置参考

### Web 配置项（web_config.yaml）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `host` | `0.0.0.0` | 监听地址 |
| `port` | `8000` | 监听端口 |
| `max_upload_size_mb` | `100` | 单文件上传大小上限 (MB) |
| `request_timeout` | `120` | 单文件处理超时 (秒) |
| `cors_origins` | `["*"]` | 允许的跨域来源 |
| `pre_warm_ocr` | `true` | 启动时预热 PaddleOCR |
| `enable_dedup` | `true` | 是否启用业务去重 |

环境变量覆盖方式（`INVOICE_WEB_` 前缀）：

```bash
export INVOICE_WEB_MAX_UPLOAD_SIZE_MB=200
export INVOICE_WEB_CORS_ORIGINS=https://app.example.com
export INVOICE_WEB_PRE_WARM_OCR=true
```

---

## 四、运维命令

```bash
# ── 启动与停止 ──
docker compose up -d              # 启动
docker compose down               # 停止并移除容器
docker compose restart            # 重启
docker compose stop               # 停止（保留容器）
docker compose start              # 启动已停止的容器

# ── 日志 ──
docker compose logs -f            # 实时日志
docker compose logs --tail=100    # 最近 100 行

# ── 更新 ──
git pull                          # 拉取最新代码
docker compose build --no-cache   # 重新构建（无缓存）
docker compose up -d              # 启动新版本

# ── 监控 ──
docker stats                      # 查看资源占用
curl http://localhost:8000/api/v1/health  # 健康检查
```

---

## 五、性能调优

| 场景 | 建议 |
|------|------|
| CPU 密集型 | 增加 `max_workers`（建议 ≤ CPU 核心数） |
| 高并发 | 前置 Nginx 做负载均衡，后端多实例 |
| GPU 加速 | `config.yaml` 中设置 `use_gpu: true`（需 NVIDIA Container Toolkit） |
| 大批量文件 | 使用 `/api/v1/batch` 异步接口，客户端轮询结果 |
| 内存不足 | 关闭 `pre_warm_ocr`，减小 `max_workers` |

---

## 六、常见问题

**Q: 启动后 `ocr_loaded: false`？**
A: PaddleOCR 预热失败，服务仍可用。首次请求时自动加载，耗时约 30 秒。

**Q: 上传文件时返回 413？**
A: 超出 `max_upload_size_mb` 限制，调大该值后重启。

**Q: 容器启动后立即退出？**
A: 检查日志 `docker compose logs`，常见原因：端口被占用、内存不足。

**Q: 如何处理海量文件？**
A: 推荐客户端循环调用 `/api/v1/extract` 并发上传，或通过 `/api/v1/batch` 分批处理。

---

## 七、API 速查

| 方法 | 路径 | 说明 | 请求格式 |
|------|------|------|----------|
| GET | `/api/v1/health` | 健康检查 | — |
| POST | `/api/v1/extract` | 单张发票识别 | `multipart/form-data` |
| POST | `/api/v1/batch` | 批量发票识别 | `multipart/form-data` |
| GET | `/api/v1/batch/{job_id}` | 任务状态查询 | — |
| GET | `/api/v1/batch/{job_id}/results` | JSON 结果 | — |
| GET | `/api/v1/batch/{job_id}/download` | Excel 下载 | — |
| GET | `/docs` | Swagger 文档 | — |
