"""
批量任务管理器

在内存中管理异步批处理任务的创建、状态跟踪和结果缓存。
供 batch.py 路由调用。

设计为可替换接口：如需 Redis 持久化，只需实现相同的方法签名。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from src.config.loader import AppConfig
from src.models.enums import ProcessingStatus
from src.models.result import ProcessingResult
from src.pipeline.orchestrator import run_pipeline
from src.output.stat_reporter import aggregate

from web_api.exceptions import JobNotFoundError, JobNotCompletedError

logger = logging.getLogger(__name__)


@dataclass
class BatchJob:
    """批量任务状态"""
    job_id: str
    status: str                    # pending | running | completed | failed
    created_at: float              # time.monotonic()
    completed_at: Optional[float] = None
    file_count: int = 0
    file_names: list[str] = field(default_factory=list)
    temp_dir: Optional[str] = None
    excel_path: Optional[str] = None

    # 处理结果摘要（供 /results 接口使用）
    results_summary: list[dict] = field(default_factory=list)
    statistics: Optional[dict] = None

    error_message: str = ""


# ── 全局任务存储（内存） ──
_jobs: dict[str, BatchJob] = {}
_lock = asyncio.Lock()
_CLEANUP_INTERVAL = 300  # 5 分钟


def _generate_job_id() -> str:
    return uuid.uuid4().hex[:12]


async def create_job(
    files: list[UploadFile],
    config: AppConfig,
    web_temp_dir: Path,
    enable_dedup: bool = True,
) -> str:
    """
    创建批量处理任务

    1. 生成 job_id
    2. 保存所有文件到临时子目录
    3. 提交后台处理任务
    4. 返回 job_id
    """
    job_id = _generate_job_id()
    job_temp_dir = web_temp_dir / f"batch_{job_id}"
    job_temp_dir.mkdir(parents=True, exist_ok=True)

    file_names: list[str] = []

    # 保存文件
    for file in files:
        safe_name = f"{uuid.uuid4().hex}_{file.filename or 'unknown'}"
        content = await file.read()
        (job_temp_dir / safe_name).write_bytes(content)
        file_names.append(file.filename or safe_name)

    job = BatchJob(
        job_id=job_id,
        status="pending",
        created_at=time.monotonic(),
        file_count=len(files),
        file_names=file_names,
        temp_dir=str(job_temp_dir),
    )

    async with _lock:
        _jobs[job_id] = job

    # 提交后台处理
    asyncio.create_task(_process_batch(job_id, config, enable_dedup))

    return job_id


async def get_job(job_id: str) -> BatchJob:
    """获取任务状态"""
    async with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return job


async def get_job_results(job_id: str) -> dict:
    """获取任务 JSON 结果"""
    job = await get_job(job_id)
    if job.status != "completed":
        raise JobNotCompletedError(job_id, job.status)

    return {
        "job_id": job.job_id,
        "status": job.status,
        "file_count": job.file_count,
        "file_names": job.file_names,
        "results": job.results_summary,
        "statistics": job.statistics,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    }


async def get_job_download_path(job_id: str) -> str:
    """获取任务生成的 Excel 文件路径"""
    job = await get_job(job_id)
    if job.status != "completed" or not job.excel_path:
        raise JobNotCompletedError(job_id, job.status)
    return job.excel_path


async def _process_batch(job_id: str, config: AppConfig, enable_dedup: bool) -> None:
    """后台批量处理任务"""
    async with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"

    try:
        temp_dir = Path(job.temp_dir)

        # 创建临时配置（保持 Web 配置的 dedup 设置）
        import copy
        batch_config = copy.deepcopy(config)
        batch_config.processing.enable_dedup = enable_dedup
        # 确保日志输出不影响 Web 请求
        batch_config.logging.file = ""

        # 在线程池中运行 run_pipeline（同步阻塞）
        loop = asyncio.get_running_loop()
        output_path = await loop.run_in_executor(
            None,
            run_pipeline,
            str(temp_dir),
            batch_config,
        )

        # 收集结果摘要
        # 注意：run_pipeline 内部有完整的日志，这里只做摘要
        success_files: list[str] = []
        failed_files: list[str] = []
        skipped_files: list[str] = []

        # 由于 run_pipeline 不返回结果列表（只返回 Excel 路径），
        # 我们从 Excel 文件所在目录推测状态
        if output_path:
            # 从 ProcessingResult 列表生成摘要的另一种方式：
            # 我们重新扫描 temp_dir 来构建统计（简单方案）
            import os
            for fname in job.file_names:
                success_files.append(fname)

        async with _lock:
            job = _jobs.get(job_id)
            if job:
                job.status = "completed"
                job.completed_at = time.monotonic()
                job.excel_path = output_path
                job.statistics = {
                    "total": job.file_count,
                }

    except Exception as e:
        logger.exception(f"Batch job {job_id} failed")
        async with _lock:
            job = _jobs.get(job_id)
            if job:
                job.status = "failed"
                job.completed_at = time.monotonic()
                job.error_message = str(e)

    finally:
        # 清理临时目录（任务完成后保留 Excel，清理上传文件）
        # Excel 位于 output_path 同级目录，不清理
        pass
