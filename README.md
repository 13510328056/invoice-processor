# 发票批处理工具 (Invoice Processor)

自动化完成电子发票的批量识别、信息提取与结构化导出。支持 **OFD**（中国电子发票国家标准格式，XML 直接解析）和 **PDF/JPG/PNG**（嵌入式文本提取 + OCR 兜底）。

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

## 快速开始

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

## 配置文件

通过 `config.yaml` 配置全部参数（参见 [config.yaml](config.yaml)）：

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

## 项目结构

```
src/
├── config/          # 配置加载 (Pydantic + YAML)
├── models/          # 数据模型 (InvoiceData, LineItem 等)
├── utils/           # 工具函数 (日志、异常、文件校验)
├── pipeline/        # 管线编排 (扫描、去重、调度)
├── parser/          # 文件解析 (OFD/OCR)
├── extractor/       # 字段提取 (正则/上下文/LLM/校验)
└── output/          # 输出 (Excel/统计)
```

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

## License

MIT
