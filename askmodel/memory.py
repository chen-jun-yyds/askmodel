import json
from datetime import datetime
from pathlib import Path

from . import config, api

SUMMARY_PROMPT = """阅读下面的项目结构和关键文件内容，生成一份"项目理解摘要"：
1. 项目是做什么的
2. 技术栈和关键依赖
3. 目录结构和各模块职责
4. 代码风格约定（命名、注释、import 方式）
Markdown 格式，500 字以内。"""

COMPRESS_PROMPT = """把下面的对话历史压缩成一段简洁记忆，保留所有关键信息
（需求、决策、代码变更、待办），去掉寒暄和重复。Markdown 格式。"""

RECENT_TURNS = 20
COMPRESS_THRESHOLD = 30
COMPRESS_BATCH = 20
SUMMARY_MIN_CHARS = 1000


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def load_summary() -> str:
    return _read(config.project_dir() / "summary.md")


def save_summary(text: str):
    (config.project_dir() / "summary.md").write_text(text, encoding="utf-8")


def load_compressed() -> str:
    return _read(config.project_dir() / "compressed.md")


def save_compressed(text: str):
    (config.project_dir() / "compressed.md").write_text(text, encoding="utf-8")


def load_history() -> list:
    p = config.project_dir() / "history.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_history(history: list):
    p = config.project_dir() / "history.json"
    p.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_project():
    """清空当前项目下的所有记忆文件，保留项目目录本身"""
    d = config.project_dir()
    for f in ("summary.md", "compressed.md", "history.json", "scan_context.json"):
        p = d / f
        if p.exists():
            p.unlink()


def generate_summary(context: str, small_cfg: dict) -> str:
    messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": context[:100000]},
    ]
    return api.chat(messages, small_cfg)


def compress_history(chunk: list, small_cfg: dict) -> str:
    text = json.dumps(chunk, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": COMPRESS_PROMPT},
        {"role": "user", "content": text},
    ]
    return api.chat(messages, small_cfg)


def build_messages(user_input: str, system_prompt: str) -> list:
    messages = [{"role": "system", "content": system_prompt}]
    summary = load_summary()
    compressed = load_compressed()

    if summary:
        messages.append({"role": "system", "content": f"# 项目理解\n{summary}"})
    else:
        ctx = config.load_scan_context()
        if ctx and len(ctx) < SUMMARY_MIN_CHARS:
            messages.append({"role": "system", "content": f"# 项目结构\n{ctx}"})

    if compressed:
        messages.append({"role": "system", "content": f"# 历史记忆\n{compressed}"})

    messages.extend(load_history()[-RECENT_TURNS:])
    messages.append({"role": "user", "content": user_input})
    return messages


def record_turn(user: str, assistant: str):
    history = load_history()
    now = datetime.now().isoformat()
    history.append({"role": "user", "content": user, "time": now})
    history.append({"role": "assistant", "content": assistant, "time": now})
    save_history(history)


def maybe_compress(small_cfg: dict) -> bool:
    history = load_history()
    if len(history) <= COMPRESS_THRESHOLD:
        return False
    old = history[:COMPRESS_BATCH]
    new_compressed = compress_history(old, small_cfg)
    existing = load_compressed()
    merged = (existing + "\n\n" + new_compressed).strip() if existing else new_compressed
    save_compressed(merged)
    save_history(history[COMPRESS_BATCH:])
    return True