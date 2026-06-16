"""
测试：业务去重模块
"""

from __future__ import annotations

import pytest

from src.models.enums import ProcessingStatus
from src.models.invoice import InvoiceData
from src.models.result import ProcessingResult, ScannedFile
from src.pipeline.dedup import deduplicate


def _make_result(rel_path: str, code: str, number: str,
                 status: ProcessingStatus = ProcessingStatus.SUCCESS) -> ProcessingResult:
    invoice = InvoiceData(
        file_path=rel_path,
        invoice_code=code,
        invoice_number=number,
    )
    return ProcessingResult(
        scanned_file=ScannedFile(
            abs_path=f"/tmp/{rel_path}",
            rel_path=rel_path,
            file_type="pdf",
        ),
        status=status,
        invoice=invoice if status != ProcessingStatus.FAILED else None,
        error_message="" if status != ProcessingStatus.FAILED else "error",
    )


class TestDeduplicate:
    """去重功能测试"""

    def test_no_duplicates(self):
        """没有重复时，所有结果保持"""
        results = [
            _make_result("a.pdf", "code1", "num1"),
            _make_result("b.pdf", "code2", "num2"),
            _make_result("c.pdf", "code3", "num3"),
        ]
        deduped = deduplicate(results)
        assert len(deduped) == 3
        assert all(r.status == ProcessingStatus.SUCCESS for r in deduped)

    def test_duplicate_same_invoice(self):
        """相同发票代码+号码时，仅保留首次"""
        results = [
            _make_result("first.pdf", "code1", "num1"),
            _make_result("second.pdf", "code1", "num1"),
        ]
        deduped = deduplicate(results)
        assert len(deduped) == 2
        assert deduped[0].status == ProcessingStatus.SUCCESS
        assert deduped[0].scanned_file.rel_path == "first.pdf"
        assert deduped[1].status == ProcessingStatus.SKIPPED

    def test_duplicate_different_invoices(self):
        """相同代码但不同号码时，不视为重复"""
        results = [
            _make_result("a.pdf", "code1", "num1"),
            _make_result("b.pdf", "code1", "num2"),
        ]
        deduped = deduplicate(results)
        assert len(deduped) == 2
        assert all(r.status == ProcessingStatus.SUCCESS for r in deduped)

    def test_duplicate_mixed_with_failed(self):
        """失败的条目不影响去重逻辑"""
        results = [
            _make_result("a.pdf", "code1", "num1"),
            _make_result("b.pdf", "code1", "num1"),
            _make_result("c.pdf", "code2", "num2", ProcessingStatus.FAILED),
        ]
        deduped = deduplicate(results)
        assert len(deduped) == 3
        assert deduped[0].status == ProcessingStatus.SUCCESS
        assert deduped[1].status == ProcessingStatus.SKIPPED
        assert deduped[2].status == ProcessingStatus.FAILED

    def test_empty_invoice_code(self):
        """发票代码为空但号码不为空时，按号码去重"""
        results = [
            _make_result("a.pdf", "", "num1"),
            _make_result("b.pdf", "", "num1"),
        ]
        deduped = deduplicate(results)
        assert deduped[1].status == ProcessingStatus.SKIPPED
