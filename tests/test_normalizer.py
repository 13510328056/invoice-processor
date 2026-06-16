"""
测试：字段规范化
"""

from __future__ import annotations

import pytest

from src.extractor.normalizer import (
    normalize_date,
    normalize_amount,
    normalize_check_code,
    normalize_fullwidth,
)


class TestNormalizeDate:
    """日期归一化测试"""

    def test_standard_chinese(self):
        assert normalize_date("2026年05月15日") == "2026-05-15"

    def test_short_chinese(self):
        assert normalize_date("2026年5月15日") == "2026-05-15"

    def test_slash_separator(self):
        assert normalize_date("2026/05/15") == "2026-05-15"

    def test_hyphen_separator(self):
        assert normalize_date("2026-05-15") == "2026-05-15"

    def test_compact_date(self):
        assert normalize_date("20260515") == "2026-05-15"

    def test_empty_string(self):
        assert normalize_date("") == ""

    def test_unrecognized_format(self):
        """无法识别的格式应返回原值"""
        assert normalize_date("15-05-2026") == "15-05-2026"


class TestNormalizeAmount:
    """金额清洗测试"""

    def test_yuan_symbol(self):
        assert normalize_amount("¥1,234.56") == "1234.56"

    def test_cny_symbol(self):
        assert normalize_amount("￥800.00") == "800.00"

    def test_dollar_symbol(self):
        assert normalize_amount("$500.00") == "500.00"

    def test_negative_amount(self):
        assert normalize_amount("-500.00") == "-500.00"

    def test_no_symbol(self):
        assert normalize_amount("1234.56") == "1234.56"

    def test_integer_amount(self):
        assert normalize_amount("1000") == "1000"

    def test_chinese_comma(self):
        assert normalize_amount("1，234.56") == "1234.56"

    def test_euro_symbol(self):
        assert normalize_amount("€999.99") == "999.99"

    def test_empty_string(self):
        assert normalize_amount("") == ""


class TestNormalizeCheckCode:
    """校验码清洗测试"""

    def test_with_spaces(self):
        assert normalize_check_code("1234 5678 9012") == "123456789012"

    def test_no_spaces(self):
        assert normalize_check_code("123456789012") == "123456789012"

    def test_empty_string(self):
        assert normalize_check_code("") == ""


class TestNormalizeFullwidth:
    """全半角统一测试"""

    def test_fullwidth_letters(self):
        assert normalize_fullwidth("ＡＢＣ") == "ABC"

    def test_fullwidth_digits(self):
        assert normalize_fullwidth("１２３") == "123"

    def test_mixed_content(self):
        assert normalize_fullwidth("ＡＢＣ１２３xyz") == "ABC123xyz"

    def test_no_conversion_needed(self):
        assert normalize_fullwidth("ABC123") == "ABC123"

    def test_empty_string(self):
        assert normalize_fullwidth("") == ""
