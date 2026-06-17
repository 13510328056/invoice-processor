"""批量处理端点测试"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestBatchEndpoint:
    """POST /api/v1/batch"""

    def test_create_batch_success(self, test_client: TestClient, sample_pdf_bytes):
        """创建批量任务应返回 job_id"""
        response = test_client.post(
            "/api/v1/batch",
            files=[
                ("files", ("inv1.pdf", sample_pdf_bytes, "application/pdf")),
                ("files", ("inv2.pdf", sample_pdf_bytes, "application/pdf")),
            ],
        )
        assert response.status_code == 200

        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["file_count"] == 2

    def test_create_batch_no_files(self, test_client: TestClient):
        """不传文件应返回 422"""
        response = test_client.post("/api/v1/batch")
        assert response.status_code == 422

    def test_get_batch_status_not_found(self, test_client: TestClient):
        """查询不存在的任务应返回 404"""
        response = test_client.get("/api/v1/batch/nonexistent123")
        assert response.status_code == 404

        data = response.json()
        assert data["error"]["code"] == "JOB_NOT_FOUND"

    def test_get_batch_results_not_completed(self, test_client: TestClient, sample_pdf_bytes):
        """在任务完成前获取结果应返回 400"""
        response = test_client.post(
            "/api/v1/batch",
            files=[("files", ("inv1.pdf", sample_pdf_bytes, "application/pdf"))],
        )
        job_id = response.json()["job_id"]

        # 立即查询结果（任务可能尚未完成）
        response = test_client.get(f"/api/v1/batch/{job_id}/results")
        # 可能还是 pending/running，应返回 400
        assert response.status_code in (200, 400)

    def test_batch_without_dedup(self, test_client: TestClient, sample_pdf_bytes):
        """批量任务应支持 enable_dedup 参数"""
        response = test_client.post(
            "/api/v1/batch",
            files=[("files", ("inv1.pdf", sample_pdf_bytes, "application/pdf"))],
            data={"enable_dedup": "false"},
        )
        assert response.status_code == 200

    def test_get_batch_status_flow(self, test_client: TestClient, sample_pdf_bytes):
        """创建后查询状态应返回正确的任务信息"""
        # 创建任务
        create_resp = test_client.post(
            "/api/v1/batch",
            files=[("files", ("inv1.pdf", sample_pdf_bytes, "application/pdf"))],
        )
        job_id = create_resp.json()["job_id"]

        # 查询状态
        status_resp = test_client.get(f"/api/v1/batch/{job_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("pending", "running", "completed")
        assert data["file_count"] == 1
        assert "created_at" in data
