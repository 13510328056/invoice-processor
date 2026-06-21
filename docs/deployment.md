# 发票识别服务 — 部署指南

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | OpenCloudOS 9.4 / RHEL 9 / CentOS Stream 9 |
| Python | ≥ 3.12 |
| 内存 | ≥ 4GB（PaddleOCR 占用 1~2GB） |
| 磁盘 | ≥ 10GB（含 PaddleOCR 模型） |
| CPU | 推荐 4 核以上 |

---

## 一、快速部署

### 1. 安装系统依赖

```bash
# OpenCloudOS / RHEL 9 / CentOS Stream 9
sudo dnf install -y epel-release
sudo dnf install -y python3.12 python3.12-devel python3.12-pip \
    mesa-libGL glib2 libgomp \
    gcc-c++ make \
    google-noto-cjk-fonts
```

各包说明：

| 包名 | 作用 |
|------|------|
| `python3.12` | Python 3.12 运行时 |
| `python3.12-devel` | Python 头文件（编译 C 扩展需要） |
| `mesa-libGL` | OpenGL 库（OpenCV/PaddleX 需要） |
| `glib2` | GLib 底层库 |
| `libgomp` | OpenMP 并行库（PaddlePaddle 需要） |
| `gcc-c++ make` | C++ 编译工具链（pip 编译 C 扩展需要） |
| `google-noto-cjk-fonts` | 中文 Noto 字体（OCR 可视化需要） |

### 2. 创建虚拟环境并安装

```bash
# 克隆仓库
git clone https://github.com/13510328056/invoice-processor.git ./invoice-processor
cd invoice-processor

# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .
```

首次安装时 pip 会自动解析并下载所有依赖（paddleocr、paddlepaddle、opencv 等），耗时取决于网络。

### 3. 按需修改配置

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

### 4. 启动 Web 服务

```bash
# 单 worker 模式（PaddleOCR 每个进程 ~1-2GB 内存）
uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --workers 1

# 开发模式（热重载）
uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --reload

# 或通过 python -m 启动
python -m web_api.main
```

首次启动时会下载 PaddleOCR 模型（约 30~60 秒），可通过健康检查确认：

```bash
curl http://localhost:8000/api/v1/health
```

预期返回：
```json
{"status":"ok","version":"1.0.0","uptime_seconds":12.34,"ocr_loaded":true}
```

### 5. 验证

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 测试单文件识别
curl -X POST http://localhost:8000/api/v1/extract \
  -F "file=@测试发票.pdf"

# 访问 API 文档
# 浏览器打开 http://localhost:8000/docs
```

### 6. 后台运行（使用 systemd）

创建 `/etc/systemd/system/invoice-processor.service`：

```ini
[Unit]
Description=发票识别服务
After=network.target

[Service]
Type=simple
User=nobody
Group=nobody
WorkingDirectory=/opt/invoice-processor
Environment=PATH=/opt/invoice-processor/.venv/bin
ExecStart=/opt/invoice-processor/.venv/bin/uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=10

# 安全限制（生产环境推荐）
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now invoice-processor

# 查看状态
sudo systemctl status invoice-processor

# 查看日志
sudo journalctl -u invoice-processor -f
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
   发票识别服务（uvicorn）
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

### 使用 Supervisor 管理进程

```bash
pip install supervisor
```

创建 `/etc/supervisord.d/invoice-processor.ini`（OpenCloudOS/RHEL 路径）：

```ini
[program:invoice-processor]
command=/opt/invoice-processor/.venv/bin/uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --workers 1
directory=/opt/invoice-processor
user=nobody
autostart=true
autorestart=true
startretries=3
stderr_logfile=/var/log/invoice-processor/err.log
stdout_logfile=/var/log/invoice-processor/out.log
environment=PATH="/opt/invoice-processor/.venv/bin"
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
# ── 安装系统依赖 ──
sudo dnf install -y mesa-libGL glib2 libgomp google-noto-cjk-fonts

# ── 启动与停止 ──
# 开发模式
uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式（后台）
nohup uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --workers 1 > app.log 2>&1 &

# systemd 方式
sudo systemctl start invoice-processor
sudo systemctl stop invoice-processor
sudo systemctl restart invoice-processor

# ── CLI 模式 ──
# 批量处理文件夹
python invoice_processor.py /path/to/invoices --config config.yaml

# ── 监控 ──
curl http://localhost:8000/api/v1/health  # 健康检查
sudo journalctl -u invoice-processor -f   # 实时日志（systemd 方式）
tail -f app.log                           # 实时日志（nohup 方式）
```

---

## 五、性能调优

| 场景 | 建议 |
|------|------|
| CPU 密集型 | 增加 `max_workers`（建议 ≤ CPU 核心数） |
| 高并发 | 前置 Nginx 做负载均衡，后端多实例 |
| GPU 加速 | `config.yaml` 中设置 `use_gpu: true`（需 NVIDIA 驱动 + CUDA） |
| 大批量文件 | 使用 `/api/v1/batch` 异步接口，客户端轮询结果 |
| 内存不足 | 关闭 `pre_warm_ocr`，减小 `max_workers` |

---

## 六、常见问题

**Q: 启动后 `ocr_loaded: false`？**
A: PaddleOCR 预热失败，常见原因及排查：
   - 缺系统库：`sudo dnf install -y mesa-libGL glib2 libgomp`
   - 模型下载超时：检查网络连接，或手动删除缓存 `rm -rf ~/.paddlex/ ~/.paddleocr/` 后重启重试

**Q: 上传文件时返回 413？**
A: 超出 `max_upload_size_mb` 限制，调大该值后重启。如前置 Nginx，也需修改 `client_max_body_size`。

**Q: 进程启动后立即退出？**
A: 检查日志，常见原因：端口被占用、内存不足、Python 依赖未完整安装。

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
