"""
发票批处理工具 — 商品明细解析与三级校验

SRS 3.2.2 E 节：三级校验
1. 商品级：SUM(金额) == 不含税金额
2. 税额级：SUM(税额) == 税额
3. 合计级：不含税金额 + 税额 == 价税合计
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.models.invoice import InvoiceData, LineItem

logger = logging.getLogger(__name__)


def validate_line_items(invoice: InvoiceData) -> list[str]:
    """
    执行商品明细三级校验

    Args:
        invoice: 发票数据（line_items 必须已填充）

    Returns:
        校验不通过的备注列表
    """
    notes: list[str] = []

    if not invoice.line_items:
        return notes

    # 解析金额和税额（转为浮点数）
    total_item_amount = 0.0
    total_item_tax = 0.0
    valid_amounts = True
    valid_taxes = True

    for item in invoice.line_items:
        try:
            total_item_amount += float(item.amount) if item.amount else 0.0
        except ValueError:
            valid_amounts = False

        try:
            total_item_tax += float(item.tax_amount) if item.tax_amount else 0.0
        except ValueError:
            valid_taxes = False

    # 获取主表值
    try:
        pretax = float(invoice.pretax_amount) if invoice.pretax_amount else 0.0
    except ValueError:
        pretax = 0.0

    try:
        tax = float(invoice.tax_amount) if invoice.tax_amount else 0.0
    except ValueError:
        tax = 0.0

    try:
        total = float(invoice.total_amount) if invoice.total_amount else 0.0
    except ValueError:
        total = 0.0

    # --- 第一级校验：商品级 ---
    if valid_amounts and pretax > 0:
        if abs(total_item_amount - pretax) > 0.01:
            msg = (
                f"商品金额合计({total_item_amount:.2f}) "
                f"≠ 不含税金额({pretax:.2f})"
            )
            notes.append(msg)
            logger.warning(f"校验失败: {msg} — {invoice.file_path}")

    # --- 第二级校验：税额级 ---
    if valid_taxes and tax > 0:
        if abs(total_item_tax - tax) > 0.01:
            msg = (
                f"商品税额合计({total_item_tax:.2f}) "
                f"≠ 主表税额({tax:.2f})"
            )
            notes.append(msg)
            logger.warning(f"校验失败: {msg} — {invoice.file_path}")

    # --- 第三级校验：合计级 ---
    if pretax > 0 and tax > 0 and total > 0:
        if abs(pretax + tax - total) > 0.01:
            msg = (
                f"不含税金额({pretax:.2f}) + 税额({tax:.2f}) "
                f"≠ 价税合计({total:.2f})"
            )
            notes.append(msg)
            logger.warning(f"校验失败: {msg} — {invoice.file_path}")

    if not notes:
        logger.debug(f"商品明细三级校验通过: {invoice.file_path}")

    return notes


def set_validation_remarks(invoice: InvoiceData) -> None:
    """
    将校验结果填入备注列

    Args:
        invoice: 发票数据（原地修改 remarks 字段）
    """
    # 合并 validation_notes 和 line_items 校验结果
    all_notes = list(invoice.validation_notes)
    all_notes.extend(validate_line_items(invoice))

    # OFD 字段缺失检查
    if invoice.extraction_source in ("ofd_xml", "ofd_fallback_ocr"):
        _check_ofd_field_completeness(invoice, all_notes)

    if all_notes:
        invoice.remarks = "；".join(all_notes)
    else:
        invoice.remarks = ""


def _check_ofd_field_completeness(invoice: InvoiceData,
                                  notes: list[str]) -> None:
    """检查 OFD 提取的字段完整性"""
    empty_fields = []
    for field_name in [
        "invoice_code", "invoice_number", "invoice_date",
        "buyer_name", "seller_name",
        "total_amount", "pretax_amount", "tax_amount",
    ]:
        if not getattr(invoice, field_name, ""):
            empty_fields.append(field_name)

    if empty_fields:
        notes.append(f"OFD字段不完整: 缺失{','.join(empty_fields)}")
