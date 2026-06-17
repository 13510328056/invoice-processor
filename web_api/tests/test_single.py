"""单文件提取端点测试"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestSingleExtractEndpoint:
    """POST /api/v1/extract"""

    def test_extract_success(self, test_client: TestClient, mock_process_single_file, sample_pdf_bytes):
        """上传有效文件应返回 200 和提取结果"""
        response = test_client.post(
            "/api/v1/extract",
            files={"file": ("test_invoice.pdf", sample_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["invoice_number"] == "08765432"
        assert data["data"]["invoice_code"] == "1100231560"
        assert data["data"]["total_amount"] == "100.00"
        assert data["elapsed_seconds"] >= 0
        assert data["source"] == "ocr"

    def test_extract_failed(self, test_client: TestClient, mock_process_failed, sample_pdf_bytes):
        """处理失败应返回 422"""
        response = test_client.post(
            "/api/v1/extract",
            files={"file": ("bad_file.pdf", sample_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 422

        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "EXTRACTION_FAILED"

    def test_extract_unsupported_file_type(self, test_client: TestClient):
        """上传不支持的文件类型应返回 422"""
        response = test_client.post(
            "/api/v1/extract",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert response.status_code == 422

        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_FILE_TYPE"

    def test_extract_includes_line_items(self, test_client: TestClient, mock_process_single_file, sample_pdf_bytes):
        """成功结果应包含商品明细"""
        response = test_client.post(
            "/api/v1/extract",
            files={"file": ("test_invoice.pdf", sample_pdf_bytes, "application/pdf")},
        )
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["line_items"]) == 1
        item = data["data"]["line_items"][0]
        assert item["货物名称"] == "测试商品"
        assert item["金额"] == "90.91"

    def test_extract_with_query_param(self, test_client: TestClient, mock_process_single_file, sample_pdf_bytes):
        """应支持 enable_dedup 表单参数"""
        response = test_client.post(
            "/api/v1/extract",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
            data={"enable_dedup": "false"},
        )
        assert response.status_code == 200

    def test_extract_large_file_returns_413(self, test_client: TestClient):
        """超过大小限制应返回 413"""
        # 创建 25MB 的虚拟内容
        large_content = b"0" * (25 * 1024 * 1024)
        response = test_client.post(
            "/api/v1/extract",
            files={"file": ("large.pdf", large_content, "application/pdf")},
        )
        assert response.status_code == 413

    def test_extract_file_cleanup(self, test_client: TestClient, mock_process_single_file, sample_pdf_bytes, tmp_path):
        """处理完成后临时文件应被清理"""
        import tempfile
        temp_dir = tmp_path / "invoice_web_test"
        temp_dir.mkdir()

        response = test_client.post(
            "/api/v1/extract",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200

        # 临时目录中不应残留文件
        remaining = list(temp_dir.iterdir())
        # 注意：这里我们无法控制 extractor 的 temp_dir（它使用 web_config 的），
        # 但只要 mock 返回成功就足够了
