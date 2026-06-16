"""
发票批处理工具 — 业务去重模块

以「发票代码 + 发票号码」为业务去重键
"""

from __future__ import annotations

import logging

from src.models.enums import ProcessingStatus
from src.models.result import ProcessingResult

logger = logging.getLogger(__name__)


def deduplicate(results: list[ProcessingResult]) -> list[ProcessingResult]:
    """
    按业务键去重：同一「发票代码+发票号码」仅保留首次成功提取的记录

    Args:
        results: 处理结果列表（含成功、失败、跳过）

    Returns:
        去重后的结果列表（重复项标记为 SKIPPED）
    """
    seen: set[tuple[str, str]] = set()
    deduped: list[ProcessingResult] = []

    for result in results:
        if result.status != ProcessingStatus.SUCCESS or not result.invoice:
            # 失败/已跳过 → 直接保留
            deduped.append(result)
            continue

        key = result.invoice.dedup_key
        if not key[0] and not key[1]:
            # 空键（代码和号码均为空）→ 无法去重，保留
            deduped.append(result)
            continue

        if key in seen:
            # 重复 → 标记为跳过
            logger.info(
                f"跳过重复发票（发票代码:{key[0]} 发票号码:{key[1]}）: "
                f"{result.scanned_file.rel_path}"
            )
            result.status = ProcessingStatus.SKIPPED
            result.error_message = (
                f"跳过重复发票（发票代码:{key[0]} 发票号码:{key[1]}）"
            )
            deduped.append(result)
        else:
            seen.add(key)
            deduped.append(result)

    if seen:
        logger.info(f"业务去重完成: 去重前={len(results)}, 去重后={len(deduped)}, "
                     f"唯一发票数={len(seen)}")

    return deduped
