"""
发票批处理工具 — OFD 格式直接解析器

中国国家标准 GB/T 33993 版式文档格式
本质：ZIP 压缩包内嵌 XML 结构化数据

数据提取策略（单一主数据源）：
CustomTag.xml → 结构化字段名 + ObjectRef ID → Content.xml → 实际文本值
"""

from __future__ import annotations

import logging
import os
import re
import time
import zipfile
from pathlib import Path
from typing import Optional

from lxml import etree

from src.config.loader import AppConfig
from src.models.result import ScannedFile, RawParseResult
from src.parser.base import InvoiceParser

logger = logging.getLogger(__name__)


# OFD 命名空间
NS_OFD = "http://www.ofdspec.org/2016"

# CustomTag.xml 标签名 → 内部字段名映射
# (标签名, 子路径, 取第几个 ID)
CUSTOMTAG_FIELD_MAP: dict[str, tuple[str, int]] = {
    "InvoiceNo": ("invoice_number", 0),
    "IssueDate": ("invoice_date", 0),
    "InvoiceCode": ("invoice_code", 0),
    "CheckCode": ("check_code", 0),
    # Buyer → BuyerName
    "BuyerName": ("buyer_name", 0),
    "BuyerTaxID": ("buyer_tax_id", 0),
    # Seller → SellerName
    "SellerName": ("seller_name", 0),
    "SellerTaxID": ("seller_tax_id", 0),
    # 金额（取第1个ID为货币符号，第2个ID为金额值）
    "TaxExclusiveTotalAmount": ("pretax_amount", 1),   # 不含税金额
    "TaxTotalAmount": ("tax_amount", 1),                # 税额
    "TaxInclusiveTotalAmount": ("total_amount", 1),     # 价税合计
}


# CustomData Name → 内部字段名（降级用）
CUSTOMDATA_FIELD_MAP: dict[str, str] = {
    "发票号码": "invoice_number",
    "开票日期": "invoice_date",
    "合计金额": "pretax_amount",
    "合计税额": "tax_amount",
    "价税合计": "total_amount",
    "发票代码": "invoice_code",
    "校验码": "check_code",
    "购买方名称": "buyer_name",
    "购买方纳税人识别号": "buyer_tax_id",
    "销售方名称": "seller_name",
    "销售方纳税人识别号": "seller_tax_id",
}


class OFDParser(InvoiceParser):
    """OFD 发票解析器"""

    def __init__(self):
        self._xpath_mapping: Optional[dict[str, str]] = None

    def parse(self, scanned_file: ScannedFile, config: AppConfig) -> RawParseResult:
        """
        解析 OFD 文件

        流程：
        1. 解析 Content.xml → 建立 ID→文本 映射
        2. 解析 CustomTag.xml → 字段名+ID → 提取所有结构化字段
        3. 降级：从 OFD.xml CustomData 补充缺失字段
        4. 提取页面文本作为正则匹配的兜底
        """
        start = time.monotonic()
        result = RawParseResult(scanned_file=scanned_file, source="ofd_xml")

        try:
            if not zipfile.is_zipfile(scanned_file.abs_path):
                result.parse_errors.append("OFD解包失败: 文件不是有效的ZIP格式")
                logger.warning(f"OFD 非 ZIP 格式: {scanned_file.rel_path}")
                return result

            with zipfile.ZipFile(scanned_file.abs_path, "r") as zf:
                namelist = zf.namelist()

                # ── 1. 建立 ID→文本 映射（从 Content.xml） ──
                id_to_text = self._build_id_text_map(zf, namelist)
                if id_to_text:
                    logger.info(f"OFD Content.xml 映射到 {len(id_to_text)} 个 ID")

                # ── 2. 从 CustomTag.xml 提取所有结构化字段 ──
                all_fields = self._extract_all_fields_from_customtags(
                    zf, namelist, id_to_text,
                )
                if all_fields:
                    logger.info(f"OFD CustomTag 提取到 {len(all_fields)} 个字段")
                else:
                    # ── 3. 降级：CustomData ──
                    all_fields = self._extract_custom_data_fields(zf, namelist)
                    if all_fields:
                        logger.info(
                            f"OFD CustomData 降级提取到 {len(all_fields)} 个字段"
                        )

                # ── 4. 提取商品明细 ──
                line_items = self._extract_line_items_from_customtags(
                    zf, namelist, id_to_text,
                )
                if line_items:
                    result.ofd_line_items = line_items
                    logger.info(f"OFD 商品明细提取到 {len(line_items)} 条")

                # ── 5. 提取页面文本（正则兜底用） ──
                page_text = self._extract_page_text(zf, namelist, id_to_text)
                if page_text:
                    result.ocr_full_text = "\n".join(page_text)
                    result.ocr_text_blocks = [
                        {"text": t, "confidence": 1.0, "source": "ofd_xml"}
                        for t in page_text
                    ]
                    result.ocr_confidence = 1.0

                # ── 6. 存储统一字段数据 ──
                result.ofd_xml_tree = all_fields  # {内部字段名: 值}

                # ── 7. 可选预览图 ──
                if config.ofd.extract_preview:
                    self._extract_preview(zf, namelist, scanned_file)

                if not all_fields and not page_text:
                    result.parse_errors.append("OFD解析失败: 未提取到任何数据")
                else:
                    logger.info(f"OFD 解析成功: {scanned_file.rel_path}")

        except zipfile.BadZipFile:
            result.parse_errors.append("OFD解包失败: ZIP损坏")
        except etree.XMLSyntaxError as e:
            result.parse_errors.append(f"OFD XML解析失败: {e}")
        except Exception as e:
            result.parse_errors.append(f"OFD解析异常: {type(e).__name__}: {e}")

        result.parser_elapsed = time.monotonic() - start
        return result

    def has_xml_tree(self, result: RawParseResult) -> bool:
        """检查解析结果是否包含有效数据"""
        return bool(result.ofd_xml_tree) or bool(result.ocr_full_text)

    # ── 核心方法 ──

    def _build_id_text_map(
        self, zf: zipfile.ZipFile, namelist: list[str],
    ) -> dict[str, str]:
        """
        从 Content.xml 提取 ID→文本 映射

        遍历所有 TextObject，收集其 ID 和文本内容。
        ¥ 符号和金额分开存储时，合并到金额值上。
        """
        content_paths = [
            n for n in namelist if n.endswith("Content.xml")
        ]
        if not content_paths:
            return {}

        ns_map = {"ofd": NS_OFD}
        id_to_text: dict[str, str] = {}

        for cp in content_paths:
            try:
                with zf.open(cp) as f:
                    tree = etree.parse(f)

                for obj in tree.xpath("//ofd:TextObject", namespaces=ns_map):
                    oid = obj.get("ID")
                    if not oid:
                        continue
                    texts = obj.xpath(".//ofd:TextCode", namespaces=ns_map)
                    full = "".join(tc.text or "" for tc in texts).strip()
                    if full and full.replace(" ", ""):
                        id_to_text[oid] = full

            except Exception as e:
                logger.debug(f"解析 Content.xml 失败 {cp}: {e}")
                continue

        return id_to_text

    def _extract_all_fields_from_customtags(
        self,
        zf: zipfile.ZipFile,
        namelist: list[str],
        id_to_text: dict[str, str],
    ) -> dict[str, str]:
        """
        从 CustomTag.xml 提取所有结构化字段

        CustomTag.xml 例子：
            <ofd:InvoiceNo><ofd:ObjectRef PageRef="...">6922</ofd:ObjectRef></ofd:InvoiceNo>
            <ofd:Buyer>
                <ofd:BuyerName><ofd:ObjectRef PageRef="...">6924</ofd:ObjectRef></ofd:BuyerName>
                <ofd:BuyerTaxID><ofd:ObjectRef PageRef="...">6926</ofd:ObjectRef></ofd:BuyerTaxID>
            </ofd:Buyer>

        Returns:
            {内部字段名: 文本值}
        """
        customtag_path = self._find_file(namelist, "CustomTag.xml")
        if not customtag_path or not id_to_text:
            return {}

        ns_map = {"ofd": NS_OFD}
        fields: dict[str, str] = {}

        try:
            with zf.open(customtag_path) as f:
                tree = etree.parse(f)

            root = tree.getroot()

            # ── 遍历 CUSTOMTAG_FIELD_MAP ──
            for tag_name, (field_name, idx) in CUSTOMTAG_FIELD_MAP.items():
                # 在当前树中查找所有 tag_name 元素的 ObjectRef
                xpath = f".//ofd:{tag_name}/ofd:ObjectRef"
                nodes = root.xpath(xpath, namespaces=ns_map)
                if nodes and idx < len(nodes) and nodes[idx].text:
                    oid = nodes[idx].text
                    value = id_to_text.get(oid, "")
                    if value:
                        fields[field_name] = value

            # ── 遍历嵌套的子标签（如 Buyer/BuyerName） ──
            # 上面已经通过完整的 tag path 查找了

            # ── 提取价税合计大写 ──
            for oid, text in id_to_text.items():
                # 仅匹配中文大写金额（必须含"圆"或"整"）
                if re.match(r"^[零壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整]+圆[整角分零]*$", text):
                    if "total_amount_cn" not in fields:
                        fields["total_amount_cn"] = text
                    break

            # ── 提取发票类型 ──
            for oid, text in id_to_text.items():
                match = re.search(
                    r"(增值税电子普通发票|增值税专用发票|电子普通发票|电子发票|卷式发票)",
                    text,
                )
                if match and "invoice_type" not in fields:
                    fields["invoice_type"] = match.group(1)

            logger.debug(f"CustomTag 提取字段: {list(fields.keys())}")
            return fields

        except Exception as e:
            logger.debug(f"提取 CustomTag 所有字段失败: {e}")
            return {}

    def _extract_custom_data_fields(
        self, zf: zipfile.ZipFile, namelist: list[str],
    ) -> dict[str, str]:
        """从 OFD.xml CustomData 提取字段（降级方案）"""
        ofd_xml_path = self._find_file(namelist, "OFD.xml")
        if not ofd_xml_path:
            return {}

        try:
            with zf.open(ofd_xml_path) as f:
                tree = etree.parse(f)

            ns_map = {"ofd": NS_OFD}
            fields: dict[str, str] = {}
            nodes = tree.xpath("//ofd:CustomData", namespaces=ns_map)
            for node in nodes:
                name = node.get("Name", "")
                text = (node.text or "").strip()
                if name and text:
                    field_name = CUSTOMDATA_FIELD_MAP.get(name)
                    if field_name:
                        fields[field_name] = text
            return fields
        except Exception as e:
            logger.debug(f"提取 CustomData 失败: {e}")
            return {}

    def _extract_page_text(
        self,
        zf: zipfile.ZipFile,
        namelist: list[str],
        id_to_text: dict[str, str],
    ) -> list[str]:
        """
        从 ID→文本 映射中按 y 坐标顺序提取页面文本

        保留页面阅读顺序（按 y 坐标排序，同行按 x 排序）
        """
        if not id_to_text:
            return []

        # 需要从 Content.xml 获取坐标信息
        content_paths = [
            n for n in namelist if n.endswith("Content.xml")
        ]
        if not content_paths:
            return list(id_to_text.values())

        ns_map = {"ofd": NS_OFD}
        items: list[tuple[float, float, str]] = []

        for cp in content_paths:
            try:
                with zf.open(cp) as f:
                    tree = etree.parse(f)

                for obj in tree.xpath("//ofd:TextObject", namespaces=ns_map):
                    oid = obj.get("ID")
                    if not oid:
                        continue
                    text = id_to_text.get(oid, "")
                    if not text:
                        continue
                    # 获取位置：从 Boundary 属性提取 y
                    boundary = obj.get("Boundary", "0 0 0 0")
                    parts = boundary.split()
                    if len(parts) >= 2:
                        try:
                            y = float(parts[1])
                        except ValueError:
                            y = 0.0
                    else:
                        y = 0.0
                    # 获取 x 位置
                    x = float(parts[0]) if parts else 0.0
                    items.append((y, x, text))

            except Exception:
                continue

        if not items:
            return list(id_to_text.values())

        # 按 y 分组，组内按 x 排序
        items.sort(key=lambda t: (t[0], t[1]))
        lines = []
        current_y = items[0][0]
        current_line: list[tuple[float, str]] = []

        for y, x, text in items:
            if abs(y - current_y) > 2:  # 新行
                current_line.sort(key=lambda p: p[0])
                lines.append(" ".join(t[1] for t in current_line).replace("¥ ", "¥"))
                current_y = y
                current_line = [(x, text)]
            else:
                current_line.append((x, text))

        if current_line:
            current_line.sort(key=lambda p: p[0])
            lines.append(" ".join(t[1] for t in current_line).replace("¥ ", "¥"))

        return lines

    def _extract_line_items_from_customtags(
        self,
        zf: zipfile.ZipFile,
        namelist: list[str],
        id_to_text: dict[str, str],
    ) -> list[dict]:
        """
        从 CustomTag.xml 提取商品明细

        CustomTag 中的 Item/TaxScheme/Amount/TaxAmount 标签
        通过 ObjectRef ID 关联到 ID→文本 映射。

        Returns:
            [{goods_name, spec_model, unit, quantity, unit_price, amount, tax_rate, tax_amount}]
        """
        customtag_path = self._find_file(namelist, "CustomTag.xml")
        if not customtag_path or not id_to_text:
            return []
        ns_map = {"ofd": NS_OFD}

        try:
            with zf.open(customtag_path) as f:
                tag_tree = etree.parse(f)

            def get_ids(tag_name: str) -> list[str]:
                nodes = tag_tree.xpath(
                    f"//ofd:{tag_name}/ofd:ObjectRef",
                    namespaces=ns_map,
                )
                return [n.text for n in nodes if n.text]

            item_ids = get_ids("Item")
            tax_scheme_ids = get_ids("TaxScheme")
            amount_ids = get_ids("Amount")
            tax_amount_ids = get_ids("TaxAmount")

            if not item_ids:
                return []

            max_count = max(
                len(item_ids), len(amount_ids),
                len(tax_scheme_ids), len(tax_amount_ids),
            )
            items: list[dict] = []

            for i in range(max_count):
                goods_name = (
                    id_to_text.get(item_ids[i], "")
                    if i < len(item_ids) else ""
                )
                amount = (
                    id_to_text.get(amount_ids[i], "")
                    if i < len(amount_ids) else ""
                )
                tax_rate = (
                    id_to_text.get(tax_scheme_ids[i], "")
                    if i < len(tax_scheme_ids) else ""
                )
                tax_amt = (
                    id_to_text.get(tax_amount_ids[i], "")
                    if i < len(tax_amount_ids) else ""
                )
                if not goods_name:
                    continue
                items.append({
                    "goods_name": goods_name,
                    "spec_model": "", "unit": "",
                    "quantity": "", "unit_price": "",
                    "amount": amount,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amt,
                })

            return items

        except Exception as e:
            logger.debug(f"提取 CustomTag 商品明细失败: {e}")
            return []

    # ── 辅助方法 ──

    def _find_file(
        self, namelist: list[str], filename: str,
    ) -> Optional[str]:
        for name in namelist:
            if name.endswith(filename):
                return name
        return None

    def _extract_preview(
        self, zf: zipfile.ZipFile, namelist: list[str],
        scanned_file: ScannedFile,
    ) -> None:
        img_exts = {".jpg", ".jpeg", ".png", ".bmp"}
        for name in namelist:
            _, ext = os.path.splitext(name)
            if ext.lower() in img_exts:
                preview_dir = os.path.join(
                    os.path.dirname(scanned_file.abs_path), ".preview",
                )
                os.makedirs(preview_dir, exist_ok=True)
                preview_path = os.path.join(
                    preview_dir,
                    os.path.basename(scanned_file.rel_path) + ext,
                )
                zf.extract(name, preview_dir)
                extracted = os.path.join(preview_dir, name)
                if os.path.exists(extracted) and extracted != preview_path:
                    os.rename(extracted, preview_path)
                logger.info(f"预览图已提取: {preview_path}")
                return
