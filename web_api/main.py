"""
发票批处理工具 — FastAPI Web 服务入口

启动方式：
    uvicorn web_api.main:app --host 0.0.0.0 --port 8000 --workers 1
    python -m web_api.main                      # 开发模式
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html


class UTF8JSONResponse(JSONResponse):
    """始终携带 charset=utf-8 的 JSON 响应，防止中文乱码"""
    media_type = "application/json; charset=utf-8"

from src.config.loader import load_config
from src.utils.logger import setup_logging

from web_api.config import WebConfig, load_web_config
from web_api.exceptions import add_exception_handlers
from web_api.routes import health as health_route
from web_api.routes import single as single_route
from web_api.routes import batch as batch_route

logger = logging.getLogger(__name__)

# ── 版本 ──
__version__ = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    # ── 启动 ──
    logger.info("=" * 50)
    logger.info("发票信息识别服务启动中...")
    logger.info(f"Version: {__version__}")

    # 设置启动时间
    health_route.set_start_time()

    # 加载配置并存入 app.state
    web_config: WebConfig = app.state.web_config
    app_config = load_config()
    app.state.app_config = app_config

    # 配置日志
    setup_logging(level=web_config.log_level, log_file="")

    logger.info(f"Web config: host={web_config.host}, port={web_config.port}")
    logger.info(f"CORS origins: {web_config.cors_origins}")
    logger.info(f"Max upload size: {web_config.max_upload_size_mb}MB")

    # 预热 OCR（可选，默认开启）
    if web_config.pre_warm_ocr:
        logger.info("预热 PaddleOCR（首次加载约 30 秒）...")
        try:
            from src.parser.ocr_parser import OCRParser
            ocr = OCRParser()
            ocr._initialize_engine()
            logger.info("PaddleOCR 预热完成")
        except Exception as e:
            logger.warning(f"PaddleOCR 预热失败（将在首次请求时加载）: {e}")

    logger.info("服务启动完成，文档地址: /docs")
    logger.info("=" * 50)

    yield

    # ── 关闭 ──
    logger.info("服务关闭中...")
    # 清理临时文件（可选）
    try:
        temp_dir = Path(web_config.temp_dir) if web_config.temp_dir else None
        if temp_dir and temp_dir.exists():
            import shutil, time
            now = time.time()
            for f in temp_dir.iterdir():
                if f.is_file() and (now - f.stat().st_mtime) > 3600:
                    f.unlink(missing_ok=True)
    except Exception:
        pass
    logger.info("服务已关闭")


def create_app(web_config: WebConfig = None) -> FastAPI:
    """
    FastAPI 应用工厂

    Args:
        web_config: Web 配置（不传则自动从默认位置加载）

    Returns:
        配置好的 FastAPI 实例
    """
    if web_config is None:
        web_config = load_web_config()

    app = FastAPI(
        title="发票信息识别服务",
        description="自动完成电子发票的批量识别、信息提取与结构化导出",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,       # 自定义 docs 页面（添加 charset）
        redoc_url=None,      # 自定义 redoc 页面
        default_response_class=UTF8JSONResponse,
        generate_unique_id_function=lambda route: route.name.replace("_", "-").replace(" ", "-"),
        swagger_ui_parameters={"deepLinking": True},
    )

    # ── 自定义 docs/redoc 页面（添加 charset=utf-8 防止中文乱码） ──
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        html = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=app.title + " - Swagger UI",
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        )
        # 注入 charset meta 标签
        body = html.body.decode("utf-8")
        body = body.replace(
            "</head>",
            '<meta charset="utf-8"></head>',
        )
        return HTMLResponse(
            content=body,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    @app.get("/redoc", include_in_schema=False)
    async def custom_redoc_html():
        html = get_redoc_html(
            openapi_url=app.openapi_url,
            title=app.title + " - ReDoc",
            redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
        )
        body = html.body.decode("utf-8")
        body = body.replace(
            "</head>",
            '<meta charset="utf-8"></head>',
        )
        return HTMLResponse(
            content=body,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    # 将 WebConfig 存入 app.state（lifespan 中可访问）
    app.state.web_config = web_config

    # ── 中间件：强制所有 JSON 响应携带 charset=utf-8 ──
    @app.middleware("http")
    async def add_utf8_charset(request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=web_config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 注册路由 ──
    app.include_router(health_route.router)
    app.include_router(single_route.router)
    app.include_router(batch_route.router)

    # ── 修正 OpenAPI schema ──
    # list[UploadFile] 在 OpenAPI 3.1 中生成 contentMediaType 而非 format:binary，
    # 某些 Swagger UI 版本将其渲染为文件数组控件而非文本输入框。
    # 如果遇到渲染问题，请参考以下方案：
    # 方案 A：在 File(..., openapi_extra={...}) 中添加 format:binary 增强兼容
    # 方案 B：改用 UploadFile 单文件上传（推荐在前端循环调用）

    # ── 注册异常处理器 ──
    add_exception_handlers(app)

    return app


# ── 全局 app 实例（供 uvicorn 导入） ──
app = create_app()


# ── 开发模式直接运行 ──
if __name__ == "__main__":
    import uvicorn

    web_config = load_web_config()
    uvicorn.run(
        "web_api.main:app",
        host=web_config.host,
        port=web_config.port,
        reload=True,
        log_level=web_config.log_level.lower(),
    )
