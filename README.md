# 发票批处理工具 (Invoice Processor)

自动化完成电子发票的批量识别、信息提取与结构化导出。支持 **OFD**（中国电子发票国家标准格式，XML 直接解析）和 **PDF/JPG/PNG**（嵌入式文本提取 + OCR 兜底）。

同时提供 **REST API 服务**，可通过 HTTP 接口远程调用发票识别能力。

---

## 功能特性

- **多格式支持**：`.ofd` `.pdf` `.jpg` `.png`
- **OFD 结构化提取**：通过 CustomTag → ID → 文本映射直取字段，准确率 ≈ 100%
- **PDF 位置感知提取**：按坐标自动合并标签-值对，支持双列布局切分
- **OCR 列感知提取**：自动识别双列布局（购买方/销售方），按 x 坐标切分左右列，正确分离购销方信息
- **竖排表格提取**：支持 OCR 识别结果中的竖排商品明细（项目名在左列，金额/税率/税额在右列），按 y 坐标分组重构行
- **字段完整提取**：21 个标准字段（发票号码、购销方信息、金额、商品明细等）
- **多级校验**：商品级/税额级/合计级三级校验
- **业务去重**：以「发票代码+发票号码」为键去重
- **并发处理**：ThreadPoolExecutor 可配置并发数
- **LLM 兜底**：支持 Qwen/Claude/Gemini 对低置信度字段进行二次提取（可选）
- **Excel 输出**：4+1 Sheet（成功/失败/跳过/统计/商品明细）
- **REST API**：FastAPI 提供 HTTP 接口，支持单文件实时识别和批量异步处理

---

## CLI 工具

### 环境要求

- Python 3.10 ~ 3.12
- 操作系统：Windows 10+ / macOS 12+ / Linux

### 安装

```bash
# 克隆仓库
git clone <repo-url>
cd invoice-processor

# 安装依赖
pip install -e .
```

### 使用

```bash
# 一键处理
python invoice_processor.py ./发票文件夹

# 详细日志
python invoice_processor.py ./发票文件夹 -v

# 图形化选择文件夹
python invoice_processor.py --gui

# 生成默认配置文件
python invoice_processor.py --init-config
```

### 输出

生成 `发票信息统计.xlsx`，包含 4 个 Sheet：

| Sheet | 内容 |
|---|---|
| 成功处理 | 22 列：文件路径、发票代码、号码、日期、购销方信息、金额、商品明细等 |
| 失败处理 | 识别失败的文件及原因 |
| 非电子发票 | 跳过的非发票文件 |
| 处理统计 | 树状汇总统计、校验关系、成功率、总耗时 |

---

## Web API 服务

提供 REST API，可通过 HTTP 远程调用发票识别功能。

### 快速启动

```bash
# 安装额外依赖
pip install fastapi uvicorn python-multipart

# 启动服务（开发模式）
uvicorn web_api.main:app --reload --port 8000

# 启动服务（生产模式）
uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### Docker 部署

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 |
| `POST` | `/api/v1/extract` | 单张发票识别（同步返回 JSON） |
| `POST` | `/api/v1/batch` | 批量发票识别（异步任务） |
| `GET` | `/api/v1/batch/{job_id}` | 查询批量任务状态 |
| `GET` | `/api/v1/batch/{job_id}/results` | 获取批量任务 JSON 结果 |
| `GET` | `/api/v1/batch/{job_id}/download` | 下载批量任务 Excel 结果 |

### API 使用示例

```bash
# 单文件识别
curl -X POST http://localhost:8000/api/v1/extract \
  -F "file=@invoice.pdf" \
  -F "enable_dedup=true"

# 批量识别
curl -X POST http://localhost:8000/api/v1/batch \
  -F "files=@invoice1.pdf" \
  -F "files=@invoice2.jpg" \
  -F "enable_dedup=true"

# 查询任务状态
curl http://localhost:8000/api/v1/batch/{job_id}
```

访问 `http://localhost:8000/docs` 查看交互式 API 文档（Swagger UI）。

### Web 配置

通过 `web_config.yaml` 配置 Web 服务参数（支持环境变量 `INVOICE_WEB_*` 覆盖）：

```yaml
web:
  host: "0.0.0.0"
  port: 8000
  max_upload_size_mb: 100    # 单文件上传限制
  pre_warm_ocr: true         # 启动时预加载 PaddleOCR
  cors_origins:
    - "*"
```

---

## 配置文件

通过 `config.yaml` 配置全部处理参数（参见 [config.yaml](config.yaml)）：

```yaml
ocr:
  engine: paddleocr         # 引擎选择
processing:
  max_workers: 4            # 并发线程数
  enable_dedup: true        # 业务去重
extraction:
  strategy: ofd+xml+ocr     # 提取策略
  llm_fallback: true        # LLM 兜底
```

---

## 项目结构

```
invoice-processor/
├── invoice_processor.py      # CLI 入口
├── config.yaml               # 处理配置
├── web_config.yaml           # Web 服务配置
├── Dockerfile                # Docker 构建文件
├── docker-compose.yml        # Docker 编排
│
├── src/                      # 核心处理模块
│   ├── config/               # 配置加载 (Pydantic + YAML)
│   ├── models/               # 数据模型 (InvoiceData, LineItem 等)
│   ├── utils/                # 工具函数 (日志、异常、文件校验)
│   ├── pipeline/             # 管线编排 (扫描、去重、调度)
│   ├── parser/               # 文件解析 (OFD/OCR)
│   ├── extractor/            # 字段提取 (正则/上下文/LLM/校验)
│   └── output/               # 输出 (Excel/统计)
│
├── web_api/                  # Web 服务模块
│   ├── main.py               # FastAPI 应用工厂
│   ├── config.py             # Web 配置模型
│   ├── exceptions.py         # 统一异常处理
│   ├── dependencies.py       # 依赖注入
│   ├── routes/               # API 路由
│   │   ├── health.py         # 健康检查
│   │   ├── single.py         # 单文件提取
│   │   └── batch.py          # 批量处理
│   ├── service/              # 业务逻辑
│   │   ├── extractor.py      # 单文件处理封装
│   │   └── batch_manager.py  # 批量任务管理
│   ├── models/               # 响应模型
│   │   └── responses.py
│   └── tests/                # Web 服务测试
│
├── tests/                    # CLI 单元测试
└── docs/
```

---

## 技术栈

| 模块 | 技术 |
|---|---|
| OFD 解析 | `lxml` + `zipfile` (CustomTag → ID → 文本) |
| PDF 处理 | `PyMuPDF` (位置感知文本提取) |
| OCR 引擎 | `PaddleOCR 2.8.1` + `PaddlePaddle 2.6.2` |
| 图像处理 | `opencv-python-headless` |
| Excel 输出 | `openpyxl` |
| LLM 集成 | `httpx` (Qwen/Claude/Gemini) |
| 配置校验 | `pydantic` |
| CLI | `argparse` |
| Web 框架 | `FastAPI` + `uvicorn` |
| 容器化 | `Docker` + `docker-compose` |

---

## License

MIT
