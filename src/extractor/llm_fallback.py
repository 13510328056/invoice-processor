"""
发票批处理工具 — LLM 兜底字段提取

策略模式：Qwen / Claude / Gemini
仅对 OCR 置信度低于阈值的字段调用
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ── Prompt 模板 ──
SYSTEM_PROMPT = """你是一个中国发票字段提取助手。
从 OCR 识别的发票文本中，提取指定字段的精确值。

规则：
1. 只返回字段值本身，不要包含任何解释
2. 如果字段值不存在或不确定，只返回 "UNSURE"
3. 金额值不要包含货币符号（¥、￥）
4. 金额值使用半角数字和点（如 1234.56）
5. 日期以 YYYY-MM-DD 格式返回"""

USER_PROMPT_TEMPLATE = """OCR 识别的发票文本：
```
{context}
```

请提取以下字段（每行一个字段名=值）：
{field_list}"""


class LLMProvider(ABC):
    """LLM 提供者抽象基类"""

    @abstractmethod
    def extract(self, field_names: list[str], context_text: str) -> dict[str, str]:
        ...


class QwenProvider(LLMProvider):
    """阿里通义千问"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or ""
        self.api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        self.model = "qwen-turbo"

    def extract(self, field_names: list[str], context_text: str) -> dict[str, str]:
        field_list = "\n".join(f"{name}=" for name in field_names)
        prompt = USER_PROMPT_TEMPLATE.format(
            context=context_text[:3000],
            field_list=field_list,
        )
        try:
            resp = httpx.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ]
                    },
                    "parameters": {"temperature": 0.1, "max_tokens": 500},
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            output = data.get("output", {}).get("text", "")
            return self._parse_output(output, field_names)
        except Exception as e:
            logger.warning(f"Qwen API 调用失败: {e}")
            return {name: "" for name in field_names}

    def _parse_output(self, text: str, field_names: list[str]) -> dict[str, str]:
        result = {}
        for line in text.strip().split("\n"):
            for name in field_names:
                if line.startswith(f"{name}="):
                    value = line[len(name) + 1:].strip()
                    result[name] = value if value != "UNSURE" else ""
                    break
        return result


class ClaudeProvider(LLMProvider):
    """Anthropic Claude"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or ""
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-sonnet-4-20250514"

    def extract(self, field_names: list[str], context_text: str) -> dict[str, str]:
        field_list = "\n".join(f"{name}=" for name in field_names)
        prompt = USER_PROMPT_TEMPLATE.format(
            context=context_text[:3000],
            field_list=field_list,
        )
        try:
            resp = httpx.post(
                self.api_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 500,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [{}])[0].get("text", "")
            return self._parse_output(content, field_names)
        except Exception as e:
            logger.warning(f"Claude API 调用失败: {e}")
            return {name: "" for name in field_names}

    def _parse_output(self, text: str, field_names: list[str]) -> dict[str, str]:
        result = {}
        for line in text.strip().split("\n"):
            for name in field_names:
                if line.startswith(f"{name}="):
                    value = line[len(name) + 1:].strip()
                    result[name] = value if value != "UNSURE" else ""
                    break
        return result


class GeminiProvider(LLMProvider):
    """Google Gemini"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or ""
        self.api_url = "https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent"

    def extract(self, field_names: list[str], context_text: str) -> dict[str, str]:
        field_list = "\n".join(f"{name}=" for name in field_names)
        prompt = USER_PROMPT_TEMPLATE.format(
            context=context_text[:3000],
            field_list=field_list,
        )
        try:
            resp = httpx.post(
                f"{self.api_url}?key={self.api_key}",
                json={
                    "contents": [{
                        "parts": [
                            {"text": SYSTEM_PROMPT + "\n\n" + prompt}
                        ]
                    }],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 500,
                    },
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            output = (data.get("candidates", [{}])[0]
                      .get("content", {})
                      .get("parts", [{}])[0]
                      .get("text", ""))
            return self._parse_output(output, field_names)
        except Exception as e:
            logger.warning(f"Gemini API 调用失败: {e}")
            return {name: "" for name in field_names}

    def _parse_output(self, text: str, field_names: list[str]) -> dict[str, str]:
        result = {}
        for line in text.strip().split("\n"):
            for name in field_names:
                if line.startswith(f"{name}="):
                    value = line[len(name) + 1:].strip()
                    result[name] = value if value != "UNSURE" else ""
                    break
        return result


class LLMExtractor:
    """LLM 提取器入口"""

    def __init__(self, provider: str = "qwen", api_key: Optional[str] = None):
        self._providers = {
            "qwen": QwenProvider,
            "claude": ClaudeProvider,
            "gemini": GeminiProvider,
        }
        provider_cls = self._providers.get(provider.lower(), QwenProvider)
        self._provider = provider_cls(api_key=api_key)

    def extract_field(self, field_name: str, context_text: str) -> str:
        """
        提取单个字段

        Args:
            field_name: 字段名
            context_text: OCR 文本上下文

        Returns:
            提取的值，不确定时返回空字符串
        """
        result = self._provider.extract([field_name], context_text)
        return result.get(field_name, "")
