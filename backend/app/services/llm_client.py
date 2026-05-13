"""Thin wrapper over an OpenAI-compatible chat API.

Configured via LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME (see .env.example).
Works with OpenAI, DeepSeek, Qwen/Bailian, OpenRouter, local servers, etc.
"""

from typing import Iterator, List, Optional

from openai import OpenAI

from ..config import Config


class LLMNotConfigured(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        if not self.api_key:
            raise LLMNotConfigured("LLM_API_KEY 未配置，请在 .env 中填写")
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: List[dict],
        temperature: float = 0.4,
        max_tokens: int = 8192,
    ) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def stream(
        self,
        messages: List[dict],
        temperature: float = 0.4,
        max_tokens: int = 8192,
    ) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None)
            if piece:
                yield piece
