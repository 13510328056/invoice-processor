"""
发票批处理工具 — OCR 解析器

支持 PDF（PyMuPDF 光栅化）、JPG/PNG 直接 OCR
"""

from __future__ import annotations

import logging
import os
import time
from io import BytesIO
from typing import Optional

import numpy as np

from src.config.loader import AppConfig
from src.models.enums import FileType
from src.models.result import ScannedFile, RawParseResult
from src.parser.base import InvoiceParser

logger = logging.getLogger(__name__)


class OCRParser(InvoiceParser):
    """OCR 发票解析器（单例模式，PaddleX 不支持重复初始化）"""

    _shared_instance = None  # 类级共享实例
    _init_failed = False     # 标记初始化失败，防止重复重试

    @classmethod
    def _get_shared_ocr(cls):
        """获取或创建全局共享的 PaddleOCR 实例"""
        if cls._shared_instance is None and not cls._init_failed:
            try:
                from paddleocr import PaddleOCR
                ocr_kwargs: dict = {}

                # 检测 init 是否接受 use_gpu（co_varnames 不含 **kwargs 捕获的变量名）
                init_vars = PaddleOCR.__init__.__code__.co_varnames
                if "use_gpu" in init_vars:
                    ocr_kwargs["use_gpu"] = False
                if "use_angle_cls" in init_vars:
                    ocr_kwargs["use_angle_cls"] = False
                ocr_kwargs.setdefault("lang", "ch")
                cls._shared_instance = PaddleOCR(**ocr_kwargs)
                logger.info("PaddleOCR 引擎初始化完成")
            except ImportError:
                logger.error("PaddleOCR 未安装，请执行: pip install paddleocr")
                raise
            except Exception as e:
                logger.error(f"PaddleOCR 初始化失败: {e}")
                cls._init_failed = True  # 标记失败，后续请求不再重试
                raise
        return cls._shared_instance

    def __init__(self):
        self._ocr_instance = None

    def _initialize_engine(self) -> None:
        """主动触发引擎加载（用于预热）"""
        _ = self._ocr

    @property
    def _ocr(self):
        """懒加载 PaddleOCR 实例（共享单例）"""
        if self._ocr_instance is None:
            self._ocr_instance = self._get_shared_ocr()
        return self._ocr_instance

    def parse(self, scanned_file: ScannedFile, config: AppConfig) -> RawParseResult:
        """
        解析文件：PDF 光栅化或图片直接送入 OCR

        Args:
            scanned_file: 扫描结果
            config: 应用配置

        Returns:
            包含 OCR 文本块的解析结果
        """
        start = time.monotonic()
        result = RawParseResult(
            scanned_file=scanned_file,
            source="ocr",
        )

        try:
            # ── 1. 优先尝试提取嵌入式文本（PDF 电子发票通常有嵌入式文字）──
            text_content, text_blocks = self._try_extract_embedded_text(scanned_file)
            if text_content and len(text_content) > 50:
                # 嵌入式文本足够多，直接使用，无需 OCR
                result.ocr_full_text = text_content
                result.ocr_text_blocks = text_blocks
                result.ocr_confidence = 1.0
                logger.debug(
                    f"PDF 嵌入式文本提取成功: {scanned_file.rel_path}, "
                    f"{len(text_content)} 字符, {len(text_blocks)} 文本块"
                )
                result.parser_elapsed = time.monotonic() - start
                return result

            # ── 2. 加载图像（PDF 光栅化 或 图片直接打开）──
            image = self._load_image(scanned_file, config)
            if image is None:
                result.parse_errors.append("图片加载失败")
                return result

            # ── 3. 图像预处理（可选，PaddleX 自带预处理管线）──
            # PaddleX 内部已包含 Normalize 等预处理步骤，对大多数清晰文档
            # 无需额外预处理。对低质量图片可取消下方注释启用。
            # processed = self._preprocess_image(image)
            # if processed is None:
            #     processed = image
            processed = image

            # 确保输入为 numpy array（PaddleOCR 不接受 PIL Image），且为 3 通道
            if not isinstance(processed, np.ndarray):
                processed = np.array(processed)
            # PaddleX Normalize 要求 3 通道图像，灰度图需扩展
            if len(processed.shape) == 2:
                import cv2
                processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
            logger.debug(f"OCR input shape: {processed.shape}")

            # ── 4. OCR 识别 ──
            try:
                ocr_result = self._ocr.ocr(processed)
                text_blocks = []

                # PaddleOCR 3.x 返回格式：list[OCRResult / dict]
                if ocr_result and isinstance(ocr_result, list) and len(ocr_result) > 0:
                    for page in ocr_result:
                        try:
                            # PaddleX OCRResult 是 dict-like 对象，支持 .get() 和 ["key"]
                            texts = page.get("rec_texts") if hasattr(page, 'get') else []
                            scores = page.get("rec_scores") if hasattr(page, 'get') else []
                            polys = page.get("rec_polys") if hasattr(page, 'get') else []
                            texts = (list(texts) if texts is not None else [])
                            scores = (list(scores) if scores is not None else [])
                            polys = (list(polys) if polys is not None else [])
                            if not texts:
                                continue
                            for i, text in enumerate(texts):
                                block = {"text": text}
                                block["confidence"] = scores[i] if i < len(scores) else 0.0
                                if len(polys) > 0 and i < len(polys):
                                    block["bbox"] = np.asarray(polys[i]).tolist()
                                text_blocks.append(block)
                        except Exception:
                            # 单页解析失败不影响其他页
                            continue
            except Exception as e:
                result.parse_errors.append(f"OCR识别失败: {e}")
                logger.warning(f"PaddleOCR 识别失败: {e}，使用嵌入式文本（如有）")
                # 如果 OCR 失败但嵌入式文本存在，回退使用
                if text_content:
                    result.ocr_full_text = text_content
                    result.ocr_text_blocks = text_blocks
                    result.ocr_confidence = 0.8
                return result

            # 确保 text_blocks 中所有值为纯 Python 类型（无 numpy scalar/array）
            for b in text_blocks:
                b["text"] = str(b["text"])
                b["confidence"] = float(b.get("confidence", 0.0))
                bbox = b.get("bbox")
                if bbox is not None and not isinstance(bbox, (list, tuple)):
                    # PaddleX 可能返回 numpy array
                    bbox = np.asarray(bbox).tolist()
                if isinstance(bbox, (list, tuple)):
                    # 统一转成 4 点格式 [[x,y], [x,y], [x,y], [x,y]]
                    if len(bbox) == 8:
                        # 扁平 8 值: [x1,y1,x2,y2,x3,y3,x4,y4]
                        bbox = [[bbox[0], bbox[1]], [bbox[2], bbox[3]],
                                [bbox[4], bbox[5]], [bbox[6], bbox[7]]]
                    elif len(bbox) == 4 and bbox[0] and isinstance(bbox[0], (list, tuple)):
                        pass  # 已经是标准 4 点格式
                    else:
                        bbox = None  # 无法处理的格式
                b["bbox"] = bbox

            # ── 5. 整理结果（添加左右列标记）──
            if text_blocks:
                # 从 bbox 计算每个文本块的中心坐标
                for b in text_blocks:
                    bbox = b.get("bbox")
                    if bbox and len(bbox) == 4:
                        xs = [p[0] for p in bbox]
                        ys = [p[1] for p in bbox]
                        b["x"] = sum(xs) / 4
                        b["y"] = sum(ys) / 4
                    else:
                        b["x"] = 0
                        b["y"] = 0

                # 按阅读顺序排序（y 容差 10px 分组，再按 x 排序）
                text_blocks.sort(key=lambda b: (round(b["y"] / 10) * 10, b["x"]))

                # 计算水平中轴（用于双列布局切分）
                x_coords = [b["x"] for b in text_blocks]
                x_min = min(x_coords)
                x_max = max(x_coords)
                x_mid = x_min + (x_max - x_min) * 0.45

                # 为每个块标注所属列
                for b in text_blocks:
                    b["side"] = "left" if b["x"] < x_mid else "right"
                    b["x_mid"] = x_mid

            full_text_parts = [b["text"] for b in text_blocks]
            total_conf = sum(b.get("confidence", 0) for b in text_blocks) if text_blocks else 0

            result.ocr_text_blocks = text_blocks
            result.ocr_full_text = "\n".join(full_text_parts)
            result.ocr_confidence = total_conf / len(text_blocks) if text_blocks else 0.0

            logger.debug(
                f"OCR 完成: {scanned_file.rel_path}, "
                f"文本块数={len(text_blocks)}, 平均置信度={result.ocr_confidence:.2f}"
            )

        except Exception as e:
            import traceback
            logger.error(f"OCR处理异常: {e}\n{''.join(traceback.format_exception(type(e), e, e.__traceback__))}")
            result.parse_errors.append(f"OCR处理异常: {type(e).__name__}: {e}")

        result.parser_elapsed = time.monotonic() - start
        return result

    # ── 辅助方法 ──

    def _load_image(self, scanned_file: ScannedFile, config: AppConfig):
        """
        加载图像：PDF 光栅化，JPG/PNG 直接打开

        PDF 加密处理：按密码列表尝试解密
        """
        from PIL import Image

        file_type = scanned_file.file_type

        # ── PDF 处理 ──
        if file_type == FileType.PDF.value:
            try:
                import fitz  # PyMuPDF

                doc = fitz.open(scanned_file.abs_path)

                # 检查加密
                if doc.is_encrypted:
                    passwords = config.processing.pdf_passwords
                    success = False
                    for pwd in passwords:
                        if doc.authenticate(pwd):
                            success = True
                            logger.info(
                                f"PDF 已用密码解密: {scanned_file.rel_path}"
                            )
                            break
                    if not success:
                        doc.close()
                        logger.warning(
                            f"PDF 加密且密码列表尝试失败: {scanned_file.rel_path}"
                        )
                        return None

                # 光栅化第一页为图像
                page = doc[0]
                zoom = 300 / 72  # 300 DPI
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                doc.close()

                img_bytes = pix.tobytes("png")
                return Image.open(BytesIO(img_bytes))

            except fitz.FileDataError:
                logger.error(f"PDF 文件损坏: {scanned_file.rel_path}")
                return None

        # ── JPG/PNG 直接打开 ──
        try:
            return Image.open(scanned_file.abs_path)
        except Exception as e:
            logger.error(f"图片打开失败 {scanned_file.rel_path}: {e}")
            return None

    def _try_extract_embedded_text(self, scanned_file: ScannedFile) -> tuple[str, list[dict]]:
        """
        尝试从 PDF 中提取嵌入式文本（无需 OCR）

        使用位置感知提取：按 y 坐标将文本分组为行，
        每组内按 x 坐标排序。同时返回坐标数据用于列切分。

        Returns:
            (full_text, text_blocks)
            text_blocks: [{"text": str, "x": float, "y": float, "side": "left"|"right"|"center"}, ...]
        """
        if scanned_file.file_type != "pdf":
            return "", []

        try:
            import fitz
            doc = fitz.open(scanned_file.abs_path)

            if doc.is_encrypted:
                if not doc.authenticate(""):
                    doc.close()
                    return "", []

            raw_lines: list[str] = []      # 未切分的原始文本行
            text_blocks: list[dict] = []    # 按 x 切分后的带坐标文本块

            for page in doc:
                blocks = page.get_text("dict")["blocks"]
                items: list[tuple[float, float, str]] = []
                for block in blocks:
                    if block["type"] != 0:
                        continue
                    for line in block["lines"]:
                        y = round(line["bbox"][1], 0)
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                x = round(span["bbox"][0], 1)
                                items.append((y, x, text))

                if not items:
                    continue
                items.sort(key=lambda t: (t[0], t[1]))

                # 页面水平中轴（用于两列布局切分）
                x_min = min(t[1] for t in items)
                x_max = max(t[1] for t in items)
                x_mid = x_min + (x_max - x_min) * 0.45

                # 构建未切分的原始文本（按 y 容差分组，与 text_blocks 一致）
                from itertools import groupby
                for y_val, group in groupby(items, key=lambda t: round(t[0] / 5) * 5):
                    line_parts = sorted(group, key=lambda t: t[1])
                    raw_lines.append(" ".join(t[2] for t in line_parts))

                # 构建切分后的 text_blocks（左/右列分离）
                current_y = items[0][0]
                current_line: list[tuple[float, str]] = []
                for y, x, text in items:
                    if abs(y - current_y) > 3:
                        self._emit_split_line(text_blocks, current_line, current_y, x_mid)
                        current_y = y
                        current_line = [(x, text)]
                    else:
                        current_line.append((x, text))
                if current_line:
                    self._emit_split_line(text_blocks, current_line, current_y, x_mid)

            doc.close()

            if text_blocks and raw_lines:
                full_text = "\n".join(raw_lines)
                return full_text, text_blocks
            return "", []

        except Exception as e:
            logger.debug(f"嵌入式文本提取失败 {scanned_file.rel_path}: {e}")
            return "", []


    @staticmethod
    def _emit_split_line(text_blocks, line_items, y, x_mid):
        """
        将一行文本按 x 中轴切分为左右两列（如适用），分别加入 text_blocks

        line_items: [(x, text), ...] 已按 x 排序
        """
        if not line_items:
            return
        left_parts = [t for x, t in line_items if x < x_mid]
        right_parts = [t for x, t in line_items if x >= x_mid]
        if left_parts and right_parts:
            # 跨列行：分别输出左右
            if left_parts:
                text_blocks.append({
                    "text": " ".join(left_parts),
                    "y": y, "x": line_items[0][0],
                    "side": "left", "x_mid": x_mid,
                })
            if right_parts:
                text_blocks.append({
                    "text": " ".join(right_parts),
                    "y": y, "x": line_items[-1][0],
                    "side": "right", "x_mid": x_mid,
                })
        else:
            # 单侧行：全部归入对应侧
            side = "left" if line_items[0][0] < x_mid else "right"
            text_blocks.append({
                "text": " ".join(t[1] for t in line_items),
                "y": y, "x": line_items[0][0],
                "side": side, "x_mid": x_mid,
            })
    def _preprocess_image(self, image) -> Optional:
        """
        图像预处理：灰度 → 自适应阈值 → 去偏斜 → 降噪

        Args:
            image: PIL Image 对象

        Returns:
            处理后的图像（PIL Image 或 numpy array），None 表示失败
        """
        try:
            import cv2
            import numpy as np

            # 转为 OpenCV 格式 (PIL → numpy)
            img = np.array(image)

            # 转灰度
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            else:
                gray = img

            # 自适应阈值二值化
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=31,
                C=2,
            )

            # 降噪
            denoised = cv2.medianBlur(binary, 3)

            return denoised

        except ImportError:
            logger.warning("OpenCV 不可用，跳过图像预处理")
            return image
        except Exception as e:
            logger.warning(f"图像预处理失败: {e}，使用原始图像")
            return image
