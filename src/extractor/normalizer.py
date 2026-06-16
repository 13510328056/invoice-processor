"""
发票批处理工具 — 字段规范化

日期统一、金额清洗、校验码清洗、全半角统一
"""

from __future__ import annotations

import re
from typing import Optional


# ── 日期格式正则 ──
DATE_PATTERNS = [
    (r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", lambda m: f"{m[0]}-{m[1].zfill(2)}-{m[2].zfill(2)}"),
    (r"(\d{4})[./](\d{1,2})[./](\d{1,2})", lambda m: f"{m[0]}-{m[1].zfill(2)}-{m[2].zfill(2)}"),
    (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: f"{m[0]}-{m[1].zfill(2)}-{m[2].zfill(2)}"),
    (r"(\d{4})(\d{2})(\d{2})", lambda m: f"{m[0]}-{m[1]}-{m[2]}"),
]


def normalize_date(raw: str) -> str:
    """
    日期归一化：将各种中文/英文日期格式统一为 YYYY-MM-DD

    Examples:
        "2026年05月15日" → "2026-05-15"
        "2026/05/15"     → "2026-05-15"
        "2026-5-15"      → "2026-05-15"
        "20260515"       → "2026-05-15"
    """
    raw = raw.strip()
    if not raw:
        return ""

    for pattern, formatter in DATE_PATTERNS:
        match = re.match(pattern, raw)
        if match:
            return formatter(match.groups())

    return raw  # 无法识别则返回原值


def normalize_amount(raw: str) -> str:
    """
    金额清洗：去除货币符号和千位分隔符，保留负号

    Examples:
        "¥1,234.56" → "1234.56"
        "￥800.00"   → "800.00"
        "-500.00"    → "-500.00"
    """
    if not raw:
        return ""
    # 去除货币符号
    s = re.sub(r"[¥￥$€£,，\s]", "", raw)
    return s


def normalize_check_code(raw: str) -> str:
    """
    校验码清洗：去除中间空格，保留连续数字

    Examples:
        "1234 5678 9012 3456 7890" → "12345678901234567890"
    """
    if not raw:
        return ""
    return re.sub(r"\s+", "", raw)


def normalize_fullwidth(text: str) -> str:
    """
    全角字母数字转半角

    Examples:
        "ＡＢＣ１２３" → "ABC123"
    """
    if not text:
        return ""

    result = []
    for char in text:
        code = ord(char)
        # 全角字母: FF21-FF3A(全角A-Z), FF41-FF5A(全角a-z)
        if 0xFF21 <= code <= 0xFF3A:
            result.append(chr(code - 0xFEE0))
        # 全角数字: FF10-FF19
        elif 0xFF10 <= code <= 0xFF19:
            result.append(chr(code - 0xFEE0))
        else:
            result.append(char)

    return "".join(result)


def normalize_field(field_name: str, value: str, config) -> str:
    """
    根据字段名和配置自动规范化

    Args:
        field_name: 字段名 (如 invoice_date, total_amount)
        value: 原始值
        config: ExtractionConfig 实例

    Returns:
        规范化后的值
    """
    if not value:
        return ""

    # 全半角统一（所有文本字段）
    value = normalize_fullwidth(value)

    date_fields = {"invoice_date"}
    amount_fields = {"total_amount", "pretax_amount", "tax_amount"}
    check_code_fields = {"check_code"}

    if field_name in date_fields and config.normalize_date:
        return normalize_date(value)
    elif field_name in amount_fields and config.normalize_amount:
        return normalize_amount(value)
    elif field_name in check_code_fields:
        return normalize_check_code(value)

    return value
