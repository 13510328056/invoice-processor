"""
发票批处理工具 — 统计聚合与控制台输出
"""

from __future__ import annotations

import logging
from typing import Optional

from src.models.enums import ProcessingStatus
from src.models.result import ProcessingResult, ProcessingStatistics

logger = logging.getLogger(__name__)


def aggregate(results: list[ProcessingResult]) -> ProcessingStatistics:
    """
    聚合统计结果

    Args:
        results: 所有文件的处理结果

    Returns:
        聚合统计数据
    """
    stats = ProcessingStatistics()
    total_elapsed = 0.0

    for r in results:
        total_elapsed += r.elapsed_seconds

        if r.scanned_file.file_type == "unsupported":
            stats.total_skipped += 1
            continue

        stats.total_invoice_files += 1

        if r.status == ProcessingStatus.SUCCESS or r.invoice is not None:
            stats.total_success += 1
        elif r.status == ProcessingStatus.FAILED:
            stats.total_failed += 1

    stats.total_scanned = len(results)
    stats.total_parse_time = total_elapsed

    return stats


def console_output(stats: ProcessingStatistics, output_filename: str) -> None:
    """
    控制台统计输出

    Args:
        stats: 统计数据
        output_filename: 输出文件名
    """
    border = "=" * 30
    print(f"\n{border}")
    print(f"      {'发票处理完成统计':^20}")
    print(f"{border}")
    print(f"共扫描文件：{stats.total_scanned} 个")
    print(f"├─ 电子发票文件：{stats.total_invoice_files} 个")
    print(f"│  ├─ 成功识别：{stats.total_success} 个")
    print(f"│  └─ 识别失败：{stats.total_failed} 个")
    print(f"└─ 非电子发票文件：{stats.total_skipped} 个")
    print()
    ok_mark = "[OK]" if stats.validation_ok else "[FAIL]"
    print(f"校验关系：{ok_mark} "
          f"{stats.total_scanned} = {stats.total_invoice_files} + {stats.total_skipped}；"
          f"{stats.total_invoice_files} = {stats.total_success} + {stats.total_failed}")
    print(f"成功率：{stats.success_rate}%")
    print(f"总耗时：{_format_duration(stats.total_wall_time)}")
    print(f"输出文件：{output_filename}")
    print(f"{border}")


def _format_duration(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}时{minutes}分{secs}秒"
    return f"{minutes}分{secs}秒"
