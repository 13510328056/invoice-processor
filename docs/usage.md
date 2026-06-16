# 发票批处理工具 — 使用手册

## 安装

```bash
pip install -e .
```

首次运行会自动下载 PaddleOCR 模型（约 500MB），请保持网络畅通。

## CLI 参数

| 参数 | 说明 | 示例 |
|---|---|---|
| `directory` | 发票文件夹路径（位置参数） | `python invoice_processor.py ./invoices` |
| `-v` / `--verbose` | 启用 DEBUG 级别日志 | `python invoice_processor.py ./invoices -v` |
| `--config <path>` | 指定配置文件 | `python invoice_processor.py ./invoices --config prod.yaml` |
| `--gui` | 图形化文件夹选择 | `python invoice_processor.py --gui` |
| `--init-config` | 生成默认 config.yaml | `python invoice_processor.py --init-config` |

## 配置文件

### 示例

```yaml
output:
  filename: "发票信息统计.xlsx"

ocr:
  engine: paddleocr        # paddleocr | tesseract | windows_ocr
  lang: ch

ofd:
  enabled: true
  mapping_path: ""         # 自定义 OFD XPath 映射文件
  fallback_to_ocr: true    # XML 解析失败时降级 OCR

processing:
  max_workers: 4           # 并发线程数 (0=串行)
  enable_dedup: true       # 发票代码+号码去重
  pdf_passwords:           # PDF 解密尝试密码列表
    - ""
    - "123456"

extraction:
  strategy: "ofd+xml+ocr"
  llm_fallback: true
  llm_provider: qwen       # qwen | claude | gemini
  confidence_threshold: 0.85

logging:
  level: INFO
  file: "processing.log"
```

## 输出字段说明（22 列）

| 列 | 字段 | 说明 |
|---|---|---|
| A | 文件路径 | 相对路径 |
| B | 发票代码 | |
| C | 发票号码 | |
| D | 开票日期 | YYYY-MM-DD |
| E | 校验码 | |
| F | 发票类型 | 电子普通发票/专用发票/卷式发票 |
| G-J | 购买方信息 | 名称/纳税人识别号/地址电话/开户行 |
| K-N | 销售方信息 | 名称/纳税人识别号/地址电话/开户行 |
| O | 价税合计（大写） | |
| P | 价税合计（小写） | |
| Q | 不含税金额 | |
| R | 税额 | |
| S | 商品明细 JSON | |
| T | 处理时间 | YYYY-MM-DD HH:MM:SS |
| U | MarkItDown 原始输出 | 默认隐藏列 |
| V | 备注 | 校验异常、LLM兜底标记等 |

## OFD XPath 映射自定义

创建 YAML 映射文件，通过 `ofd.mapping_path` 指定：

```yaml
# custom_mapping.yaml
invoice_code: "//Invoice/InvoiceCode"
invoice_number: "//Invoice/InvoiceNo"
buyer_name: "//Invoice/BuyerName"
seller_name: "//Invoice/SellerName"
total_amount: "//Invoice/TotalAmount"
```

## 常见问题

**Q: OFD 文件提取后某些字段为空？**  
A: 不同开票系统使用的 OFD XML 结构可能略有差异。可通过自定义 XPath 映射适配。

**Q: PDF 提取失败，提示"无法识别发票号码或价税合计"？**  
A: 确认 PDF 是否为电子发票（有嵌入式文本而非纯扫描件），扫描件需要 PaddleOCR。

**Q: Excel 文件被占用无法写入？**  
A: 关闭已打开的 Excel 文件后重试，工具会自动重试 3 次。

**Q: 截图或扫描件中购销方信息提取混乱？**  
A: 工具现在支持双列布局自动切分。如果购买方在左列、销售方在右列，工具会按 x 坐标自动分离并在各自的列内匹配字段。如果仍不正确，请检查图片中两个区块的 x 坐标是否有明显分界。

**Q: 商品明细提取为空？**  
A: 对于 OCR 识别的图片，工具支持竖排表格提取（项目名在左列、金额/税率/税额在右列）。如果明细为空，确认图片中商品信息区没有被其他文字干扰导致未能正确识别表头（项目名称）。
