from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .models import FileOp, ModelConfig


@dataclass
class ChatResult:
    content: str = ""
    thinking: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_hit_tokens: Optional[int] = None
    elapsed: float = 0.0
    raw: Optional[dict] = None


class ChatError(Exception):
    pass


def _extract_json_text(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.S)
    if m:
        text = m.group(1).strip()

    if not (text.startswith("[") or text.startswith("{")):
        starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
        if starts:
            start = min(starts)
            end = max(text.rfind("]"), text.rfind("}"))
            if end > start:
                text = text[start : end + 1]

    #text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    #text = re.sub(r",(\s*[\]}])", r"\1", text)
    return text.strip()


def parse_ops(text: str) -> list[FileOp]:
    candidate = _extract_json_text(text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ChatError(f"JSON 解析失败: {e}\n原始输出:\n{text[:500]}") from e

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ChatError(f"JSON 顶层不是数组或对象: {type(data).__name__}")

    ops: list[FileOp] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ChatError(f"第 {i} 条不是对象: {item!r}")
        try:
            ops.append(FileOp.model_validate(item))
        except Exception as e:
            raise ChatError(f"第 {i} 条字段非法: {e}") from e
    
    # 允许空数组，代表模型主动结束
    return ops


class ModelClient:
    def __init__(self, cfg: ModelConfig, timeout: float = 120.0):
        self.cfg = cfg
        self.timeout = timeout

    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> ChatResult:
        url = self.cfg.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = url + "/chat/completions"

        payload = {
            "model": self.cfg.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"

        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            t0 = time.time()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                elapsed = time.time() - t0

                if resp.status_code == 429:
                    wait_time = 5 * attempt
                    print(f"\n[系统提示] 触发频率限制(429)，等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    raise ChatError(f"HTTP 429: {resp.text[:300]}")
                elif resp.status_code >= 500:
                    time.sleep(3 * attempt)
                    raise ChatError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                elif resp.status_code >= 400:
                    raise ChatError(f"HTTP {resp.status_code}: {resp.text[:300]}")

                data = resp.json()
                return self._to_result(data, elapsed)
            except (httpx.HTTPError, ChatError, json.JSONDecodeError) as e:
                last_err = e
                if attempt < max_retries:
                    continue
        raise ChatError(f"调用失败（重试 {max_retries} 次）: {last_err}")

    def _to_result(self, data: dict, elapsed: float) -> ChatResult:
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError) as e:
            raise ChatError(f"返回结构异常: {data}") from e

        content = msg.get("content") or ""
        thinking = msg.get("reasoning_content") or msg.get("reasoning") or None
        usage = data.get("usage") or {}
        cache_hit = (
            usage.get("prompt_cache_hit_tokens")
            or usage.get("cache_read_input_tokens")
            or usage.get("cached_tokens")
        )
        return ChatResult(
            content=content,
            thinking=thinking,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cache_hit_tokens=cache_hit,
            elapsed=elapsed,
            raw=data,
        )