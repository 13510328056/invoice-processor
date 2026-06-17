"""健康检查端点测试"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """GET /api/v1/health"""

    def test_health_returns_ok(self, test_client: TestClient):
        """健康检查应返回 200 和 status=ok"""
        response = test_client.get("/api/v1/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["uptime_seconds"] >= 0
        assert "ocr_loaded" in data

    def test_health_schema_has_required_fields(self, test_client: TestClient):
        """响应应包含所有必需字段"""
        response = test_client.get("/api/v1/health")
        data = response.json()

        required = ["status", "version", "uptime_seconds", "ocr_loaded"]
        for field in required:
            assert field in data, f"Missing field: {field}"
