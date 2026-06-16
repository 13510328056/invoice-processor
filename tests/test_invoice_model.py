"""
测试：InvoiceData 数据模型
"""

from __future__ import annotations

import json

from src.models.invoice import InvoiceData, LineItem
from src.models.enums import FileType, ProcessingStatus, MagicNumber, EXTENSION_MAP


class TestInvoiceData:
    """发票数据模型测试"""

    def test_is_success_with_required_fields(self):
        invoice = InvoiceData(invoice_number="N001", total_amount="100.00")
        assert invoice.is_success is True

    def test_is_success_missing_number(self):
        invoice = InvoiceData(invoice_number="", total_amount="100.00")
        assert invoice.is_success is False

    def test_is_success_missing_amount(self):
        invoice = InvoiceData(invoice_number="N001", total_amount="")
        assert invoice.is_success is False

    def test_dedup_key(self):
        invoice = InvoiceData(invoice_code="C001", invoice_number="N001")
        assert invoice.dedup_key == ("C001", "N001")

    def test_to_excel_row_length(self):
        invoice = InvoiceData(file_path="test.pdf")
        row = invoice.to_excel_row()
        assert len(row) == 22  # SRS 3.3.2 规定的 22 列

    def test_set_processing_time(self):
        invoice = InvoiceData()
        invoice.set_processing_time()
        assert len(invoice.processing_time) == 19  # YYYY-MM-DD HH:MM:SS

    def test_extraction_source_default(self):
        invoice = InvoiceData()
        assert invoice.extraction_source == ""


class TestLineItem:
    """商品明细模型测试"""

    def test_to_dict(self):
        item = LineItem(
            goods_name="电脑主机",
            spec_model="标准版",
            unit="台",
            quantity="2",
            unit_price="3500.00",
            amount="7000.00",
            tax_rate="13%",
            tax_amount="910.00",
        )
        d = item.to_dict()
        assert d["货物名称"] == "电脑主机"
        assert d["金额"] == "7000.00"

    def test_from_dict(self):
        d = {
            "货物名称": "显示器",
            "规格型号": "27寸",
            "单位": "台",
            "数量": "1",
            "单价": "2500.00",
            "金额": "2500.00",
            "税率": "13%",
            "税额": "325.00",
        }
        item = LineItem.from_dict(d)
        assert item.goods_name == "显示器"
        assert item.amount == "2500.00"

    def test_empty_defaults(self):
        item = LineItem()
        assert item.goods_name == ""
        assert item.amount == ""


class TestFileTypeEnum:
    """文件类型枚举测试"""

    def test_extension_map(self):
        assert EXTENSION_MAP[".pdf"] == FileType.PDF
        assert EXTENSION_MAP[".ofd"] == FileType.OFD
        assert EXTENSION_MAP[".jpg"] == FileType.JPG
        assert EXTENSION_MAP[".png"] == FileType.PNG
        assert ".txt" not in EXTENSION_MAP


class TestMagicNumber:
    """Magic Number 测试"""

    def test_check_pdf(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(b"%PDF-1.4 test content")
            path = f.name

        try:
            assert MagicNumber.check(path, MagicNumber.PDF) is True
        finally:
            import os
            os.unlink(path)

    def test_check_not_matching(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"plain text content")
            path = f.name

        try:
            assert MagicNumber.check(path, MagicNumber.PDF) is False
        finally:
            import os
            os.unlink(path)
