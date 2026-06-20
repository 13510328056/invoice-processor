"""
发票批处理工具 — 字段提取引擎

OFD 路径：XPath 映射直取
OCR 路径：正则→关键字→LLM 兜底三级递进
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from src.config.loader import AppConfig
from src.models.invoice import InvoiceData, LineItem
from src.models.result import RawParseResult
from src.parser.ofd_parser import OFDParser
from src.extractor.normalizer import normalize_field

logger = logging.getLogger(__name__)


# ── OCR 字段正则模式 ──
# 每个字段配置 2-3 个正则，依次尝试

FIELD_PATTERNS: dict[str, list[str]] = {
    # 发票基本信息
    "invoice_code": [
        r"发票代码[：:＝=\s]*([A-Z0-9]{6,20})",
        r"发票代码\s*[：:]\s*([A-Z0-9]+)",
    ],
    "invoice_number": [
        r"发票号码[：:＝=\s]*(\d{15,25})",
        r"发票号码[：:＝=\s]*(\d{6,20})",
        r"发票号码\s*[：:]\s*(\d+)",
        r"No[：:＝=\s]*(\d+)",
    ],
    "invoice_date": [
        r"开票日期[：:＝=\s]*(\d{4}[\-/年]\d{1,2}[\-/月]\d{1,2}[日]?)",
        r"开票日期[：:＝=\s]*(\S+)",
        r"日期[：:＝=\s]*(\d{4}[\-/年]\d{1,2}[\-/月]\d{1,2})",
    ],
    "check_code": [
        r"校验码[：:＝=\s]*([0-9\s]{6,30})",
        r"校验码\s*[：:]\s*(\S+)",
    ],
    "invoice_type": [
        r"(增值税电子普通发票|增值税专用发票|电子普通发票|卷式发票|通行费发票)",
        r"(普通发票|专用发票|电子发票)",
    ],
    # 金额合计
    "total_amount_cn": [
        r"([一-鿿零壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整]+圆[整角分]*)",  # 纯大写金额（优先，不受布局顺序影响）
        r"价税合计[（(]大写[）)]\s*[：:＝=\s]*([一-鿿零壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整]+)",
        r"价税合计[（(]大写[）)][：:＝=\s]*(\S+)",
    ],
    "total_amount": [
        r"价税合计[（(]小写[）)][：:＝=\s]*[¥￥]?\s*([\d,]+\.?\d*)",
        r"价税合计[（(]小写[）)][：:＝=\s]*(\S+)",
        r"价税合计[：:＝=\s]*[¥￥]?\s*([\d,]+\.?\d*)",
        r"（小写）[^¥]*[¥￥]\s*(\d+\.\d{2})",           # ...（小写）...¥730.00
        r"[¥￥]\s*(\d+\.\d{2})(?![\s\S]*[¥￥]\s*\d+\.\d{2})",  # 最后一个 ¥X.XX
        r"[¥￥]\s*(\d+\.\d{2})\s*$",                     # 行末的 ¥金额
    ],
    "pretax_amount": [
        r"不含税金额[：:＝=　\s]*[¥￥]?\s*([\d,]+\.?\d*)",
        r"不含税[：:＝=　\s]*[¥￥]?\s*([\d,]+\.?\d*)",
        r"金额[：:＝=　\s]*[¥￥]?\s*([\d,]+\.?\d*)",
        r"合\s*计[　\s]*[¥￥]?\s*([\d,]+\.?\d*)",            # 合 计 ¥722.77
        r"合计[　\s]*[¥￥]?\s*([\d,]+\.?\d*)",
    ],
    "tax_amount": [
        r"税\s*额[：:＝=　\s]*[¥￥]?\s*([\d,]+\.?\d*)",      # 税 额 ¥7.23
        r"合\s*计[　\s]*[¥￥]?\s*[\d,]+\.?\d*[　\s]*[¥￥]?\s*([\d,]+\.?\d*)",  # 合 计 ¥X ¥Y 第2个
        r"税额[：:＝=　\s]*[¥￥]?\s*([\d,]+\.?\d*)",
        r"税额[：:＝=　\s]*(\S+)",
    ],
    # 购销方名称（补充模式：处理 OFD 仅值无标签 和 PDF 缩写标签）
    "buyer_name": [
        r"购\s*名称[：:＝=\s]*(\S+(?:有限公司|有限责任公司|厂|店|社|集团|部))",
        r"购买方[^：:：＝=]*名称[：:＝=\s]*(\S+(?:有限公司|有限责任公司|厂|店|社|集团|部))",
        r"购方[：:＝=\s]*名称[：:＝=\s]*(\S+(?:有限公司|有限责任公司|厂|店|社|集团|部))",
        r"名称[：:＝=\s]*(\S+(?:有限公司|有限责任公司|厂|店|社|集团|部))",
    ],
    "seller_name": [
        r"销\s*名称[：:＝=\s]*(\S+(?:有限公司|有限责任公司|厂|店|社|集团|部))",
        r"销售方[^：:]*名称[：:＝=\s]*(\S+(?:有限公司|有限责任公司|厂|店|社|集团|部))",
        r"销方[：:＝=\s]*名称[：:＝=\s]*(\S+(?:有限公司|有限责任公司|厂|店|社|集团|部))",
    ],
}

# 购买方/销售方上下文匹配标签（含简写和同行场景）
BUYER_MARKERS = ["购买方", "购方", "购", "买方", "付款方"]
SELLER_MARKERS = ["销售方", "销方", "销", "卖方", "收款方"]

# 子字段标签
SECTION_FIELD_MAP: dict[str, list[tuple[str, str]]] = {
    "buyer": [
        ("buyer_name", r"(名称|Name)[：:＝=\s]*(\S+)"),
        ("buyer_tax_id", r"(\w{18})\s+统一社会信用代码"),   # 值在前（PDF两列布局）
        ("buyer_tax_id", r"(纳税人识别号|税号|统一社会信用代码|TaxID)[：:＝=\s]*(\w{18})"),
        ("buyer_address_phone", r"(地址电话|地址|电话)[：:＝=\s]*(\S+)"),
        ("buyer_bank_account", r"(开户行及账号|开户行|账号|银行账号)[：:＝=\s]*(\S+)"),
    ],
    "seller": [
        ("seller_name", r"(名称|Name)[：:＝=\s]*(\S+)"),
        ("seller_tax_id", r"(\w{18})\s+统一社会信用代码"),   # 值在前（PDF两列布局）
        ("seller_tax_id", r"(纳税人识别号|税号|统一社会信用代码|TaxID)[：:＝=\s]*(\w{18})"),
        ("seller_address_phone", r"(地址电话|地址|电话)[：:＝=\s]*(\S+)"),
        ("seller_bank_account", r"(开户行及账号|开户行|账号|银行账号)[：:＝=\s]*(\S+)"),
    ],
}

# 商品明细 OCR 正则（含 PDF 纵向表格式）
LINE_ITEM_HEADER_PATTERN = r"(货物|商品|劳务|服务|项目)名称"
# 柔性行列解析：同一行中捕获 名称+金额+税率+税额（其余字段可选）
LINE_ITEM_ROW_PATTERN = (
    r"(\S+)"                     # 名称 (必须)
    r"(?:\s+\S*)?"               # 规格型号 (可选)
    r"(?:\s+\S*)?"               # 单位 (可选)
    r"(?:\s+\S*)?"               # 数量 (可选)
    r"(?:\s+\S*)?"               # 单价 (可选)
    r"\s+(\d+\.?\d*)"            # 金额 (必须)
    r"\s+(\S+)"                  # 税率 (必须)
    r"\s+(\d+\.?\d*)"            # 税额 (必须)
)


def extract_fields(result: RawParseResult, config: AppConfig) -> InvoiceData:
    """
    从解析结果中提取发票字段

    Args:
        result: 解析结果（OFD XML 树或 OCR 文本）
        config: 应用配置

    Returns:
        提取的发票数据
    """
    invoice = InvoiceData()
    invoice.file_path = result.scanned_file.rel_path
    invoice.extraction_source = result.source
    invoice.set_processing_time()

    # ── OFD 路径：CustomTag 结构化字段优先 ──
    if result.source == "ofd_xml" and isinstance(result.ofd_xml_tree, dict):
        ofd_fields: dict = result.ofd_xml_tree  # {内部字段名: 值}

        # 直接从 CustomTag 取值（已映射为内部字段名）
        for field_name, value in ofd_fields.items():
            if value:
                setattr(invoice, field_name, normalize_field(field_name, value, config.extraction))

        # 页面文本补充缺失字段（正则）
        if result.ocr_full_text:
            _apply_regex_patterns(result.ocr_full_text, invoice, config)

        # OFD 商品明细：CustomTag 结构化数据
        if result.ofd_line_items:
            _apply_ofd_line_items(result.ofd_line_items, invoice, config)
        elif result.ocr_full_text:
            _extract_line_items(result.ocr_full_text, invoice)

        logger.info(
            f"OFD 提取完成: {result.scanned_file.rel_path}, "
            f"CustomTag={len(ofd_fields)} 字段, "
            f"商品明细={len(result.ofd_line_items)} 条"
        )
        return invoice

    # ── OCR 路径：三级递进 ──
    if result.ocr_full_text:
        _apply_regex_patterns(result.ocr_full_text, invoice, config)
        _extract_section_fields_from_text(
            result.ocr_full_text, invoice, result.ocr_text_blocks,
        )
        _extract_line_items(result.ocr_full_text, invoice, result.ocr_text_blocks)

        # LLM 兜底（低于置信度阈值的字段）
        if (config.extraction.llm_fallback
                and result.ocr_confidence < config.extraction.confidence_threshold):
            _llm_fallback(result, invoice, config)

        logger.info(
            f"OCR 提取完成: {result.scanned_file.rel_path}, "
            f"置信度={result.ocr_confidence:.2f}"
        )

    return invoice


def _get_mapping(config: AppConfig) -> dict[str, str]:
    """获取 XPath 映射表"""
    from src.parser.ofd_parser import DEFAULT_XPATH_MAPPING

    mapping_path = config.ofd.mapping_path
    if not mapping_path:
        return dict(DEFAULT_XPATH_MAPPING)

    import yaml
    from pathlib import Path
    mapping_file = Path(mapping_path)
    if mapping_file.exists():
        with open(mapping_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if isinstance(raw, dict):
            return raw

    return dict(DEFAULT_XPATH_MAPPING)


def _normalize_text_layout(text: str) -> str:
    """
    标准化文本布局：将跨行的标签-值对合并到同一行

    电子发票 PDF 的嵌入式文本常出现：
        发票号码：
        26952000002270325331
    合并为：
        发票号码：26952000002270325331
    """
    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # 如果当前行以标点结尾（：:＝＝=），且下一行有非空内容
        if re.search(r"[：:＝=，,]$", line):
            # 查找下一个非空行
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                next_line = lines[j].strip()
                # 如果下一行不是标签开头，合并
                if not re.match(r"^[：:＝=]", next_line) and len(next_line) > 1:
                    result.append(f"{line} {next_line}")
                    i = j + 1
                    continue
        result.append(line)
        i += 1
    return "\n".join(result)


def _fill_ofd_buyer_seller_from_text(
    full_text: str,
    ofd_fields: dict[str, str],
    invoice: InvoiceData,
) -> None:
    """
    OFD Content.xml 文本中提取购销方名称（基于固定排列顺序）

    OFD Content.xml 的 TextCode 按阅读顺序排列：
    发票号码 → 开票日期 → 购买方名称 → 购买方纳税人识别号 → 销售方名称 → 销售方税号

    利用已从 CustomData 获取的纳税人识别号反向定位公司名称
    """
    if not full_text:
        return

    buyer_tax_id = ofd_fields.get("buyer_tax_id", "")
    seller_tax_id = ofd_fields.get("seller_tax_id", "")

    if not buyer_tax_id and not seller_tax_id:
        return

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
    company_pattern = re.compile(r"^[一-鿿()（）×]+(?:有限公司|有限责任公司|厂|店|社|集团|部|中心)$")

    for i, line in enumerate(lines):
        # 购买方：税号上方的公司名
        if buyer_tax_id and buyer_tax_id in line and not invoice.buyer_name:
            for j in range(i - 1, -1, -1):
                if company_pattern.match(lines[j]):
                    invoice.buyer_name = lines[j]
                    break
        # 销售方：税号上方的公司名
        if seller_tax_id and seller_tax_id in line and not invoice.seller_name:
            for j in range(i - 1, -1, -1):
                if company_pattern.match(lines[j]) and lines[j] != invoice.buyer_name:
                    invoice.seller_name = lines[j]
                    break


def _apply_ofd_line_items(
    line_items_data: list[dict],
    invoice: InvoiceData,
    config: AppConfig,
) -> None:
    """
    将 OFD CustomTag 提取的结构化商品明细写入 InvoiceData

    同时回填不含税金额和税额（如果尚未提取）
    """
    if not line_items_data:
        return

    items: list[LineItem] = []
    total_amount = 0.0
    total_tax = 0.0

    for raw in line_items_data:
        goods_name = raw.get("goods_name", "")
        amount = raw.get("amount", "0")
        tax_rate = raw.get("tax_rate", "")
        tax_amt = raw.get("tax_amount", "0")

        item = LineItem(
            goods_name=goods_name,
            spec_model=raw.get("spec_model", ""),
            unit=raw.get("unit", ""),
            quantity=raw.get("quantity", ""),
            unit_price=raw.get("unit_price", ""),
            amount=amount,
            tax_rate=tax_rate,
            tax_amount=tax_amt,
        )
        items.append(item)

        try:
            if amount:
                total_amount += float(amount)
        except ValueError:
            pass
        try:
            if tax_amt:
                total_tax += float(tax_amt)
        except ValueError:
            pass

    invoice.line_items = items
    import json
    invoice.line_items_json = json.dumps(
        [it.to_dict() for it in items],
        ensure_ascii=False,
    )

    # 回填不含税金额和税额（如尚未提取）
    if not invoice.pretax_amount and total_amount > 0:
        invoice.pretax_amount = f"{total_amount:.2f}"
    if not invoice.tax_amount and total_tax > 0:
        invoice.tax_amount = f"{total_tax:.2f}"


def _apply_regex_patterns(text: str, invoice: InvoiceData,
                          config: AppConfig) -> None:
    """对文本应用正则模式，提取发票字段（第一级）"""
    # 预处理：合并跨行标签-值对
    text = _normalize_text_layout(text)

    for field_name, patterns in FIELD_PATTERNS.items():
        if getattr(invoice, field_name):  # 已有值则跳过
            continue
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                setattr(invoice, field_name, normalize_field(field_name, value, config.extraction))
                break


def _extract_section_fields_from_text(
    text: str,
    invoice: InvoiceData,
    text_blocks: list[dict] | None = None,
) -> None:
    """
    从纯文本/坐标数据中按区块提取购买方/销售方子字段（第二级）

    处理三种布局：
    1. 分行布局：购买方和销售方在不同行区域（OFD）
    2. 同行布局：购名称：X 销名称：Y 在同一行
    3. 左右列布局：购/销左右并列（PDF 两列），需 x 坐标切分
    """
    # ── 优先使用 x 坐标切分左右列 ──
    if text_blocks and any(b.get("side") for b in text_blocks if "side" in b):
        for section_key, markers in [("buyer", BUYER_MARKERS), ("seller", SELLER_MARKERS)]:
            target_side = "left" if section_key == "buyer" else "right"
            column_text = "\n".join(
                b["text"] for b in text_blocks
                if b.get("side") == target_side
            )
            if column_text:
                for field_name, pattern in SECTION_FIELD_MAP.get(section_key, []):
                    if getattr(invoice, field_name):
                        continue
                    match = re.search(pattern, column_text)
                    if match:
                        setattr(invoice, field_name, match.group(match.lastindex).strip())
        return

    # ── 无 x 坐标时，使用行文本提取 ──
    lines = text.split("\n")
    for section_key, markers in [("buyer", BUYER_MARKERS), ("seller", SELLER_MARKERS)]:
        other_markers = SELLER_MARKERS if section_key == "buyer" else BUYER_MARKERS
        section_start = -1
        for i, line in enumerate(lines):
            if any(marker in line for marker in markers):
                section_start = i
                break
        if section_start < 0:
            continue

        line_with_both = lines[section_start]
        has_both = any(m in line_with_both for m in markers) and any(m in line_with_both for m in other_markers)

        if has_both:
            for field_name, pattern in SECTION_FIELD_MAP.get(section_key, []):
                if getattr(invoice, field_name):
                    continue
                match = re.search(pattern, line_with_both)
                if match:
                    setattr(invoice, field_name, match.group(match.lastindex).strip())

        section_end = len(lines)
        for i in range(section_start + 1, len(lines)):
            if any(m in lines[i] for m in other_markers):
                section_end = i
                break

        section_text = "\n".join(lines[section_start:section_end])
        for field_name, pattern in SECTION_FIELD_MAP.get(section_key, []):
            if getattr(invoice, field_name):
                continue
            match = re.search(pattern, section_text)
            if match:
                setattr(invoice, field_name, match.group(match.lastindex).strip())


def _extract_line_items(text: str, invoice: InvoiceData,
                        text_blocks: list[dict] | None = None) -> None:
    """
    从文本中提取商品明细

    支持：
    1. 标签式：货物名称：电脑主机 金额：3500.00 税额：455.00
    2. 表格式：项目名称 | 金额 | 税率 | 税额（含空格分隔的 PDF 表格）
    3. 坐标式（OCR 竖排表格）：项目名称在左列，金额/税率/税额在右列
    """
    if not text:
        return

    lines = text.split("\n")
    header_idx = -1
    for i, line in enumerate(lines):
        if re.search(LINE_ITEM_HEADER_PATTERN, line):
            header_idx = i
            break

    if header_idx < 0:
        return

    items = []
    for line in lines[header_idx + 1:]:
        line = line.strip()
        if not line or re.match(r"^[合计总计小计合\s]", line):
            break
        # 尝试匹配行列（新柔性模式：4组捕获）
        match = re.match(LINE_ITEM_ROW_PATTERN, line)
        if match:
            items.append(LineItem(
                goods_name=match.group(1),
                spec_model="",
                unit="",
                quantity="",
                unit_price="",
                amount=match.group(2),
                tax_rate=match.group(3),
                tax_amount=match.group(4),
            ))

    # 单行模式未匹配到且坐标数据可用 → 尝试坐标式竖排提取
    if not items and text_blocks:
        items = _extract_line_items_from_blocks(text_blocks)

    if items:
        invoice.line_items = items
        invoice.line_items_json = json.dumps(
            [it.to_dict() for it in items],
            ensure_ascii=False,
        )
        # 从第一条商品明细中提取金额和税额（如尚未提取）
        first = items[0]
        if not invoice.pretax_amount and first.amount:
            invoice.pretax_amount = first.amount
        if not invoice.tax_amount and first.tax_amount:
            invoice.tax_amount = first.tax_amount


# ── 表头关键字：坐标式提取时跳过 ──
LINE_ITEM_HEADER_KEYWORDS = frozenset({
    "规格型号", "单位", "数量", "单价", "金额",
    "税率", "税额", "税率/征收率", "单",
})


def _extract_line_items_from_blocks(text_blocks: list[dict]) -> list[LineItem]:
    """
    基于坐标的竖排商品明细提取

    OCR 常把表格识别为竖排（项目名在左列，金额/税率/税额在右列的不同行），
    利用 side 标记和 y 坐标分组来重构商品明细行。
    """
    # 1. 找到表头
    header_idx = -1
    for i, b in enumerate(text_blocks):
        if re.search(LINE_ITEM_HEADER_PATTERN, b.get("text", "")):
            header_idx = i
            break
    if header_idx < 0:
        return []

    header_y = round(text_blocks[header_idx].get("y", 0) / 20) * 20

    # 2. 收集表头之后的数据块（到合计区域为止）
    data_texts: list[dict] = []
    for b in text_blocks[header_idx + 1:]:
        text = b.get("text", "").strip()
        y_grp = round(b.get("y", 0) / 20) * 20
        side = b.get("side", "left")

        # 到达合计/汇总区 → 停止
        if text in ("合", "计", "合计") or text.startswith("合计") or re.match(r"^[¥￥]", text):
            break
        if text in LINE_ITEM_HEADER_KEYWORDS or len(text) <= 1:
            continue

        data_texts.append({
            "text": text,
            "y": y_grp,
            "side": side,
            "x": b.get("x", 0),
        })

    if not data_texts:
        return []

    # 3. 按 y 分组，每组 = 一行（可能跨左右列）
    groups: dict[int, dict[str, list[str]]] = {}
    for d in data_texts:
        y = d["y"]
        if y not in groups:
            groups[y] = {"left": [], "right": []}
        groups[y][d["side"]].append(d["text"])

    # 4. 构建商品明细
    items: list[LineItem] = []
    for y in sorted(groups):
        g = groups[y]
        left_texts = g["left"]
        right_texts = g["right"]

        # 左列 = 商品名称
        goods_name = left_texts[0] if left_texts else ""

        # 右列 = [金额, 税率, 税额] 或空
        amount = ""
        tax_rate = ""
        tax_amount = ""
        for t in right_texts:
            if t.endswith("%"):
                tax_rate = t
            elif re.match(r"^\d+\.?\d*$", t):
                if not amount:
                    amount = t
                elif not tax_amount:
                    tax_amount = t
            elif not amount and re.match(r"^[\d,]+\.?\d*$", t.replace(",", "")):
                amount = t

        if goods_name and amount:
            items.append(LineItem(
                goods_name=goods_name,
                amount=amount,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
            ))

    return items


def _llm_fallback(result: RawParseResult, invoice: InvoiceData,
                  config: AppConfig) -> None:
    """LLM 兜底：对低置信度字段进行调用（预留）"""
    # OCR 字段低于置信度阈值时调用 LLM
    # 实际实现依赖 src/extractor/llm_fallback.py
    # 此处不做实际调用，仅打标记
    low_conf_fields = []
    for field_name in FIELD_PATTERNS:
        if not getattr(invoice, field_name, ""):
            low_conf_fields.append(field_name)

    if low_conf_fields:
        logger.debug(
            f"LLM 兜底待处理字段: {low_conf_fields} — "
            f"文件: {result.scanned_file.rel_path}"
        )
        try:
            from src.extractor.llm_fallback import LLMExtractor
            extractor = LLMExtractor(provider=config.extraction.llm_provider)
            for field_name in low_conf_fields:
                value = extractor.extract_field(
                    field_name=field_name,
                    context_text=result.ocr_full_text,
                )
                if value and value != "UNSURE":
                    setattr(
                        invoice, field_name,
                        normalize_field(field_name, value, config.extraction),
                    )
                    invoice.validation_notes.append(f"LLM兜底提取: {field_name}")
        except Exception as e:
            logger.warning(f"LLM 兜底失败: {e}")
