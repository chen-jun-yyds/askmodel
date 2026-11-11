from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Mode(str, Enum):
    WORK = "work"
    CHAT = "chat"


class ModelConfig(BaseModel):
    base_url: str
    model_name: str
    api_key: str = ""

    def masked(self) -> dict[str, str]:
        return {
            "base_url": self.base_url,
            "model_name": self.model_name,
            "api_key": "***" if self.api_key else "(empty)",
        }


class GlobalConfig(BaseModel):
    main: Optional[ModelConfig] = None
    asit: Optional[ModelConfig] = None
    max_times: int = 3
    mode: Mode = Mode.WORK


class ProjectConfig(BaseModel):
    main: Optional[ModelConfig] = None
    asit: Optional[ModelConfig] = None
    mode: Optional[Mode] = None


class FileOp(BaseModel):
    action: str
    path: Optional[str] = None
    content: Optional[str] = None
    original: Optional[str] = None
    current: Optional[str] = None
    near_line: Optional[int] = None
    reason: Optional[str] = None


class OpResult(BaseModel):
    action: str
    path: Optional[str] = None
    ok: bool
    message: str
    content: Optional[str] = None


class CallRecord(BaseModel):
    round: int
    system_prompt: Optional[str] = None
    input_text: str
    thinking: Optional[str] = None
    output: list[FileOp] = Field(default_factory=list)
    op_results: list[OpResult] = Field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_hit_tokens: Optional[int] = None
    elapsed: float = 0.0
    raw: Optional[dict] = None


class ConversationRecord(BaseModel):
    conversation_id: str
    timestamp: datetime
    mode: Mode
    user_input: str
    project: str
    cwd: str
    calls: list[CallRecord] = Field(default_factory=list)


class RecentEntry(BaseModel):
    mode: Mode
    user_input: str
    model_output: str