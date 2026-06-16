"""
测试：商品明细校验
"""

from __future__ import annotations

import json

import pytest

from src.models.invoice import InvoiceData, LineItem
from src.extractor.line_items import validate_line_items, set_validation_remarks


class TestValidateLineItems:
    """商品明细三级校验测试"""

    def test_all_valid(self):
        """所有校验通过"""
        invoice = InvoiceData(
            file_path="test.pdf",
            pretax_amount="7000.00",
            tax_amount="910.00",
            total_amount="7910.00",
            line_items=[
                LineItem(amount="7000.00", tax_amount="910.00"),
            ],
        )
        notes = validate_line_items(invoice)
        assert len(notes) == 0

    def test_amount_mismatch(self):
        """商品金额和不等于不含税金额"""
        invoice = InvoiceData(
            file_path="test.pdf",
            pretax_amount="7000.00",
            tax_amount="910.00",
            total_amount="7910.00",
            line_items=[
                LineItem(amount="6500.00", tax_amount="910.00"),
            ],
        )
        notes = validate_line_items(invoice)
        assert any("商品金额合计" in n for n in notes)

    def test_tax_mismatch(self):
        """商品税额和不等于主表税额"""
        invoice = InvoiceData(
            file_path="test.pdf",
            pretax_amount="7000.00",
            tax_amount="910.00",
            total_amount="7910.00",
            line_items=[
                LineItem(amount="7000.00", tax_amount="800.00"),
            ],
        )
        notes = validate_line_items(invoice)
        assert any("商品税额合计" in n for n in notes)

    def test_total_mismatch(self):
        """不含税金额+税额≠价税合计"""
        invoice = InvoiceData(
            file_path="test.pdf",
            pretax_amount="7000.00",
            tax_amount="910.00",
            total_amount="8000.00",  # 应为 7910
            line_items=[
                LineItem(amount="7000.00", tax_amount="910.00"),
            ],
        )
        notes = validate_line_items(invoice)
        assert any("价税合计" in n for n in notes)

    def test_multiple_items(self):
        """多项商品明细"""
        invoice = InvoiceData(
            file_path="test.pdf",
            pretax_amount="10500.00",
            tax_amount="1365.00",
            total_amount="11865.00",
            line_items=[
                LineItem(amount="7000.00", tax_amount="910.00"),
                LineItem(amount="3500.00", tax_amount="455.00"),
            ],
        )
        notes = validate_line_items(invoice)
        assert len(notes) == 0

    def test_empty_line_items(self):
        """无商品明细"""
        invoice = InvoiceData(file_path="test.pdf")
        notes = validate_line_items(invoice)
        assert len(notes) == 0

    def test_validation_remarks_combined(self):
        """set_validation_remarks 合并备注"""
        invoice = InvoiceData(
            file_path="test.pdf",
            pretax_amount="7000.00",
            tax_amount="910.00",
            total_amount="8000.00",
            line_items=[
                LineItem(amount="7000.00", tax_amount="910.00"),
            ],
            validation_notes=["LLM兜底提取: invoice_date"],
        )
        set_validation_remarks(invoice)
        assert "LLM兜底提取" in invoice.remarks
        assert "价税合计" in invoice.remarks
