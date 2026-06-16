"""
发票批处理工具 — InvoiceData 数据模型

定义 SRS 3.2 节规定的 21 个发票字段 + 商品明细
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import ExtractionSource


@dataclass
class LineItem:
    """商品明细条目"""
    goods_name: str = ""
    spec_model: str = ""
    unit: str = ""
    quantity: str = ""
    unit_price: str = ""
    amount: str = ""          # 金额（不含税）
    tax_rate: str = ""
    tax_amount: str = ""      # 税额

    def to_dict(self) -> dict:
        return {
            "货物名称": self.goods_name,
            "规格型号": self.spec_model,
            "单位": self.unit,
            "数量": self.quantity,
            "单价": self.unit_price,
            "金额": self.amount,
            "税率": self.tax_rate,
            "税额": self.tax_amount,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LineItem":
        return cls(
            goods_name=d.get("货物名称", ""),
            spec_model=d.get("规格型号", ""),
            unit=d.get("单位", ""),
            quantity=d.get("数量", ""),
            unit_price=d.get("单价", ""),
            amount=d.get("金额", ""),
            tax_rate=d.get("税率", ""),
            tax_amount=d.get("税额", ""),
        )


@dataclass
class InvoiceData:
    """
    完整发票数据记录 — SRS 规定的 21 个字段

    Section A: 发票基本信息 (5+1 字段)
    Section B: 购买方信息 (4 字段)
    Section C: 销售方信息 (4 字段)
    Section D: 金额合计信息 (4 字段)
    Section E: 商品明细
    """
    # ── 文件元数据 ──
    file_path: str = ""                    # 文件相对路径
    processing_time: str = ""              # 处理时间 YYYY-MM-DD HH:MM:SS
    extraction_source: str = ""            # ExtractionSource 值

    # ── Section A: 发票基本信息 ──
    invoice_type: str = ""                 # 发票类型
    invoice_code: str = ""                 # 发票代码
    invoice_number: str = ""               # 发票号码
    invoice_date: str = ""                 # 开票日期 (YYYY-MM-DD)
    check_code: str = ""                   # 校验码

    # ── Section B: 购买方信息 ──
    buyer_name: str = ""                   # 购买方名称
    buyer_tax_id: str = ""                 # 购买方纳税人识别号
    buyer_address_phone: str = ""          # 购买方地址电话
    buyer_bank_account: str = ""           # 购买方开户行及账号

    # ── Section C: 销售方信息 ──
    seller_name: str = ""                  # 销售方名称
    seller_tax_id: str = ""                # 销售方纳税人识别号
    seller_address_phone: str = ""         # 销售方地址电话
    seller_bank_account: str = ""          # 销售方开户行及账号

    # ── Section D: 金额合计信息 ──
    total_amount_cn: str = ""              # 价税合计（大写）
    total_amount: str = ""                 # 价税合计（小写）
    pretax_amount: str = ""                # 不含税金额
    tax_amount: str = ""                   # 税额

    # ── Section E: 商品明细 ──
    line_items_json: str = "[]"            # JSON 字符串
    line_items: list[LineItem] = field(default_factory=list)

    # ── 辅助字段 ──
    raw_markdown: str = ""                 # 原始 Markdown 文本 (U 列)
    remarks: str = ""                      # 备注 (V 列)
    is_dedup: bool = False                 # 是否为重复发票（跳过）
    validation_notes: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """判断是否识别成功：必须包含发票号码 + 价税合计（小写）"""
        return bool(self.invoice_number) and bool(self.total_amount)

    @property
    def dedup_key(self) -> tuple[str, str]:
        """业务去重键：发票代码 + 发票号码"""
        return (self.invoice_code, self.invoice_number)

    def set_processing_time(self) -> None:
        """设置当前时间为处理时间"""
        self.processing_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_excel_row(self) -> list:
        """转换为 Excel 行数据（22 列，与 SRS 3.3.2 列定义一致）"""
        return [
            self.file_path,               # A
            self.invoice_code,            # B
            self.invoice_number,          # C
            self.invoice_date,            # D
            self.check_code,              # E
            self.invoice_type,            # F
            self.buyer_name,              # G
            self.buyer_tax_id,            # H
            self.buyer_address_phone,     # I
            self.buyer_bank_account,      # J
            self.seller_name,             # K
            self.seller_tax_id,           # L
            self.seller_address_phone,    # M
            self.seller_bank_account,     # N
            self.total_amount_cn,         # O
            self.total_amount,            # P
            self.pretax_amount,           # Q
            self.tax_amount,              # R
            self.line_items_json,         # S
            self.processing_time,         # T
            self.raw_markdown,            # U (隐藏列)
            self.remarks,                 # V
        ]
