"""Web API 测试 fixtures"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.config.loader import AppConfig, ProcessingConfig, ExtractionConfig
from src.models.enums import ProcessingStatus
from src.models.invoice import InvoiceData, LineItem
from src.models.result import ProcessingResult, ScannedFile

from web_api.config import WebConfig
from web_api.main import create_app


@pytest.fixture
def web_config() -> WebConfig:
    """测试用 WebConfig（关闭预加载）"""
    return WebConfig(
        pre_warm_ocr=False,
        max_upload_size_mb=20,
        cleanup_stale_temp_hours=0,
    )


@pytest.fixture
def app_config() -> AppConfig:
    """测试用 AppConfig（串行模式、关闭LLM）"""
    return AppConfig(
        processing=ProcessingConfig(max_workers=0, enable_dedup=False),
        extraction=ExtractionConfig(llm_fallback=False),
    )


@pytest.fixture
def test_client(web_config: WebConfig) -> Generator[TestClient, None, None]:
    """FastAPI 测试客户端"""
    app = create_app(web_config=web_config)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_process_single_file() -> Generator[MagicMock, None, None]:
    """Mock process_single_file 返回成功结果"""
    invoice = InvoiceData(
        file_path="test_invoice.pdf",
        invoice_code="1100231560",
        invoice_number="08765432",
        invoice_date="2026-05-15",
        check_code="12345678901234567890",
        invoice_type="增值税电子普通发票",
        buyer_name="购买方A",
        buyer_tax_id="91110000MA12345678",
        buyer_address_phone="北京市朝阳区 010-88888888",
        seller_name="销售方B",
        seller_tax_id="91110000MA87654321",
        seller_address_phone="上海市浦东新区 021-66666666",
        total_amount_cn="壹佰元整",
        total_amount="100.00",
        pretax_amount="90.91",
        tax_amount="9.09",
        line_items=[LineItem(
            goods_name="测试商品",
            spec_model="标准版",
            unit="个",
            quantity="1",
            unit_price="90.91",
            amount="90.91",
            tax_rate="10%",
            tax_amount="9.09",
        )],
        extraction_source="ocr",
    )
    invoice.set_processing_time()

    scanned = ScannedFile(
        abs_path="/tmp/test_invoice.pdf",
        rel_path="test_invoice.pdf",
        file_type="pdf",
    )

    result = ProcessingResult(
        scanned_file=scanned,
        status=ProcessingStatus.SUCCESS,
        invoice=invoice,
        elapsed_seconds=0.5,
    )

    with patch("web_api.service.extractor.process_single_file", return_value=result) as mock:
        yield mock


@pytest.fixture
def mock_process_failed() -> Generator[MagicMock, None, None]:
    """Mock process_single_file 返回失败结果"""
    scanned = ScannedFile(
        abs_path="/tmp/bad_file.pdf",
        rel_path="bad_file.pdf",
        file_type="pdf",
    )
    result = ProcessingResult(
        scanned_file=scanned,
        status=ProcessingStatus.FAILED,
        error_message="无法识别发票号码或价税合计",
        elapsed_seconds=0.3,
    )

    with patch("web_api.service.extractor.process_single_file", return_value=result) as mock:
        yield mock


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """模拟一个 PDF 文件内容（非真实 PDF，仅用于测试文件上传）"""
    return b"%PDF-1.4 fake pdf content for testing"
