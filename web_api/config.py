"""
Web 服务专属配置模型

独立于现有 config.yaml（AppConfig），控制 Web 层行为。
支持环境变量覆盖（前缀 INVOICE_WEB_），便于 Docker 部署。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class WebConfig(BaseModel):
    """Web 服务配置"""

    host: str = "0.0.0.0"
    port: int = 8000

    # ── 上传限制 ──
    max_upload_size_mb: int = Field(default=100, ge=1, le=1000)
    allowed_extensions: list[str] = Field(
        default=[".ofd", ".pdf", ".jpg", ".jpeg", ".png"],
    )

    # ── 请求处理 ──
    request_timeout: int = Field(default=120, ge=10, le=600)

    # ── CORS ──
    cors_origins: list[str] = ["*"]

    # ── 处理选项 ──
    enable_dedup: bool = True
    pre_warm_ocr: bool = True   # 启动时预加载 PaddleOCR

    # ── 临时文件 ──
    temp_dir: str = ""           # 空 = 使用系统临时目录
    cleanup_stale_temp_hours: int = Field(default=1, ge=0)

    # ── 日志 ──
    log_level: str = "INFO"

    @field_validator("temp_dir", mode="before")
    @classmethod
    def resolve_temp_dir(cls, v: str) -> str:
        if v:
            Path(v).mkdir(parents=True, exist_ok=True)
        return v


def load_web_config(path: Optional[str] = None) -> WebConfig:
    """
    加载 Web 配置，支持环境变量覆盖（INVOICE_WEB_ 前缀）。

    优先级：环境变量 > YAML 文件 > 代码默认值
    """
    cfg = WebConfig()  # 先取代码默认值

    if path and Path(path).exists():
        import yaml
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if raw and "web" in raw:
            web_raw = raw["web"]
            for key, val in web_raw.items():
                if hasattr(cfg, key) and val is not None:
                    setattr(cfg, key, val)

    # 环境变量覆盖（INVOICE_WEB_ 前缀）
    env_prefix = "INVOICE_WEB_"
    for field_name in cfg.model_fields:
        env_key = f"{env_prefix}{field_name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            field_info = cfg.model_fields[field_name]
            target_type = field_info.annotation
            # 简单类型转换
            if target_type is bool or target_type == bool:
                parsed = env_val.lower() in ("true", "1", "yes")
            elif target_type is int or target_type == int:
                parsed = int(env_val)
            elif target_type is list or "list" in str(target_type):
                parsed = [x.strip() for x in env_val.split(",") if x.strip()]
            else:
                parsed = env_val
            setattr(cfg, field_name, parsed)

    return cfg
