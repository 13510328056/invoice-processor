"""
发票批处理工具 — 管线编排器

协调扫描、解析、提取、去重、输出的全流程
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.config.loader import AppConfig
from src.models.enums import ProcessingStatus
from src.models.result import ProcessingResult, ProcessingStatistics, ScannedFile
from src.models.invoice import InvoiceData

from src.pipeline.scanner import scan_directory, classify_files
from src.pipeline.dedup import deduplicate

from src.parser.ofd_parser import OFDParser
from src.parser.ocr_parser import OCRParser

from src.extractor.field_matcher import extract_fields
from src.extractor.line_items import set_validation_remarks

from src.output.excel_writer import ExcelWriter
from src.output.stat_reporter import aggregate, console_output

logger = logging.getLogger(__name__)


def run_pipeline(root_dir: str, config: AppConfig) -> Optional[str]:
    """
    运行完整处理管线

    Args:
        root_dir: 根目录路径
        config: 应用配置

    Returns:
        输出文件路径（成功），None（失败）
    """
    wall_start = time.monotonic()

    # ── Phase 1: 扫描 ──
    logger.info("=" * 40)
    logger.info("阶段 1/4: 扫描文件夹")
    logger.info("=" * 40)

    try:
        scanned = scan_directory(
            root_dir=root_dir,
            skip_directories=config.processing.skip_directories,
            enable_magic_check=False,  # 默认关闭，后续可配
        )
    except (FileNotFoundError, NotADirectoryError) as e:
        logger.error(f"扫描失败: {e}")
        return None

    ofd_files, ocr_files, unsupported = classify_files(scanned)
    all_invoice_files = ofd_files + ocr_files

    logger.info(f"  ├─ OFD 文件: {len(ofd_files)}")
    logger.info(f"  ├─ OCR 文件: {len(ocr_files)}")
    logger.info(f"  └─ 非发票文件: {len(unsupported)}")

    if not all_invoice_files:
        logger.warning("未发现电子发票文件")

    # ── Phase 2: 解析 + 提取 ──
    logger.info("=" * 40)
    logger.info("阶段 2/4: 解析与字段提取")
    logger.info("=" * 40)

    results: list[ProcessingResult] = []

    # 非发票文件直接标记
    for f in unsupported:
        results.append(ProcessingResult(
            scanned_file=f,
            status=ProcessingStatus.SKIPPED,
            error_message="非电子发票格式",
        ))

    # 并发处理发票文件
    max_workers = config.processing.max_workers
    serial_mode = max_workers == 0
    if serial_mode:
        max_workers = 1

    logger.info(f"并发处理: {'串行' if serial_mode else f'max_workers={max_workers}'}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {}

        for f in all_invoice_files:
            future = executor.submit(process_single_file, f, config)
            future_to_file[future] = f

        for future in as_completed(future_to_file):
            f = future_to_file[future]
            try:
                result = future.result(timeout=config.ocr.timeout + 60)
                results.append(result)
                _log_file_result(result)
            except TimeoutError:
                results.append(ProcessingResult(
                    scanned_file=f,
                    status=ProcessingStatus.FAILED,
                    error_message="处理超时",
                ))
                logger.error(f"[FAILED] {f.rel_path} 处理超时")
            except Exception as e:
                results.append(ProcessingResult(
                    scanned_file=f,
                    status=ProcessingStatus.FAILED,
                    error_message=f"未预期异常: {type(e).__name__}: {e}",
                ))
                logger.error(f"[FAILED] {f.rel_path} 异常: {e}")

    # ── Phase 3: 去重 ──
    logger.info("=" * 40)
    logger.info("阶段 3/4: 业务去重")
    logger.info("=" * 40)

    if config.processing.enable_dedup:
        results = deduplicate(results)
    else:
        logger.info("去重已关闭")

    # ── Phase 4: 统计 + 输出 ──
    logger.info("=" * 40)
    logger.info("阶段 4/4: 写入输出文件")
    logger.info("=" * 40)

    stats = aggregate(results)
    stats.total_wall_time = time.monotonic() - wall_start

    try:
        writer = ExcelWriter(config)
        output_path = writer.write(results, stats)
    except Exception as e:
        logger.error(f"Excel 写入失败: {e}")
        return None

    # 控制台统计
    console_output(stats, str(output_path))

    logger.info(f"处理完成，总耗时: {stats.total_wall_time:.1f}秒")

    return str(output_path)


def process_single_file(scanned_file: ScannedFile,
                        config: AppConfig) -> ProcessingResult:
    """
    处理单个发票文件

    Args:
        scanned_file: 扫描文件信息
        config: 应用配置

    Returns:
        处理结果
    """
    start = time.monotonic()

    try:
        # ── 1. 解析 ──
        if scanned_file.file_type == "ofd":
            ofd_parser = OFDParser()
            parsed = ofd_parser.parse(scanned_file, config)

            # OFD 解析失败 → OCR 降级
            if (parsed.parse_errors
                    and config.ofd.fallback_to_ocr
                    and not ofd_parser.has_xml_tree(parsed)):
                logger.info(f"OFD 降级 OCR: {scanned_file.rel_path}")
                # 尝试从 OFD 提取内嵌图片进行 OCR
                import zipfile, tempfile, os
                from PIL import Image
                extracted = None
                if zipfile.is_zipfile(scanned_file.abs_path):
                    with zipfile.ZipFile(scanned_file.abs_path) as zf:
                        for name in zf.namelist():
                            if any(name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp")):
                                tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1], delete=False)
                                tmp.write(zf.read(name))
                                tmp.close()
                                extracted = tmp.name
                                break
                if extracted:
                    # 创建一个临时 ScannedFile 指向提取的图片
                    from src.models.result import ScannedFile
                    img_file = ScannedFile(
                        abs_path=extracted,
                        rel_path=scanned_file.rel_path + "_ocr",
                        file_type=os.path.splitext(extracted)[1][1:],
                    )
                    ocr_parser = OCRParser()
                    parsed = ocr_parser.parse(img_file, config)
                    parsed.source = "ofd_fallback_ocr"
                    # 清理临时文件
                    try:
                        os.unlink(extracted)
                    except Exception:
                        pass
                else:
                    parsed.source = "ofd_fallback_ocr"
        else:
            ocr_parser = OCRParser()
            parsed = ocr_parser.parse(scanned_file, config)

        # ── 2. 字段提取 ──
        invoice = extract_fields(parsed, config)

        # ── 3. 校验与备注 ──
        set_validation_remarks(invoice)

        # ── 4. 成功/失败判定 ──
        elapsed = time.monotonic() - start

        if invoice.is_success:
            return ProcessingResult(
                scanned_file=scanned_file,
                status=ProcessingStatus.SUCCESS,
                invoice=invoice,
                elapsed_seconds=elapsed,
            )
        else:
            error_msg = "无法识别发票号码或价税合计"
            if parsed.parse_errors:
                error_msg = f"{error_msg}（解析错误: {';'.join(parsed.parse_errors)}）"
            return ProcessingResult(
                scanned_file=scanned_file,
                status=ProcessingStatus.FAILED,
                error_message=error_msg,
                elapsed_seconds=elapsed,
            )

    except Exception as e:
        elapsed = time.monotonic() - start
        return ProcessingResult(
            scanned_file=scanned_file,
            status=ProcessingStatus.FAILED,
            error_message=f"处理异常: {type(e).__name__}: {e}",
            elapsed_seconds=elapsed,
        )


def _log_file_result(result: ProcessingResult) -> None:
    """记录单文件处理结果"""
    elapsed = result.elapsed_seconds

    if result.status == ProcessingStatus.SUCCESS:
        logger.info(
            f"[SUCCESS] {result.scanned_file.rel_path} 提取成功 ({elapsed:.1f}s)"
        )
    elif result.status == ProcessingStatus.FAILED:
        logger.error(
            f"[FAILED] {result.scanned_file.rel_path} "
            f"提取失败: {result.error_message}"
        )
    else:
        logger.info(
            f"[SKIPPED] {result.scanned_file.rel_path} "
            f"跳过: {result.error_message}"
        )
