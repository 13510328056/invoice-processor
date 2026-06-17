"""
统一异常处理

所有 Web API 异常继承 WebAPIError，由全局异常处理器统一
序列化为标准化 JSON 错误响应。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_UTF8_HEADERS = {"Content-Type": "application/json; charset=utf-8"}


class WebAPIError(Exception):
    """Web API 异常基类"""

    def __init__(
        self,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        message: str = "Internal server error",
        details: str = "",
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(self.message)


class FileTooLargeError(WebAPIError):
    def __init__(self, max_mb: int):
        super().__init__(
            status_code=413,
            code="FILE_TOO_LARGE",
            message=f"File exceeds maximum upload size of {max_mb}MB",
        )


class InvalidFileTypeError(WebAPIError):
    def __init__(self, filename: str, allowed: list[str]):
        super().__init__(
            status_code=422,
            code="INVALID_FILE_TYPE",
            message=f"Unsupported file type: {filename}",
            details=f"Allowed extensions: {', '.join(allowed)}",
        )


class ProcessingFailedError(WebAPIError):
    def __init__(self, detail: str = ""):
        super().__init__(
            status_code=422,
            code="EXTRACTION_FAILED",
            message="Could not extract invoice fields",
            details=detail,
        )


class ProcessingTimeoutError(WebAPIError):
    def __init__(self, timeout_s: int):
        super().__init__(
            status_code=504,
            code="PROCESSING_TIMEOUT",
            message=f"Processing timed out after {timeout_s}s",
        )


class JobNotFoundError(WebAPIError):
    def __init__(self, job_id: str):
        super().__init__(
            status_code=404,
            code="JOB_NOT_FOUND",
            message=f"Batch job not found: {job_id}",
        )


class JobNotCompletedError(WebAPIError):
    def __init__(self, job_id: str, status: str):
        super().__init__(
            status_code=400,
            code="JOB_NOT_COMPLETED",
            message=f"Batch job {job_id} is {status}, not yet completed",
        )


def add_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI app"""

    @app.exception_handler(WebAPIError)
    async def webapi_error_handler(_request: Request, exc: WebAPIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            headers=_UTF8_HEADERS,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            headers=_UTF8_HEADERS,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "details": str(exc),
                },
            },
        )
