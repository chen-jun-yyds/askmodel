import json
import requests

SYSTEM_PROMPT = """你是代码生成助手。我会给你项目理解摘要、历史记忆和最近对话。
严格模仿现有风格生成代码。

只返回 JSON，不要解释。根据操作类型返回不同格式：

【单个操作】
{
  "action": "write" | "delete" | "move" | "none",
  ... 对应字段 ...
}

【多个操作】当一次需求需要多个操作时，用数组：
{
  "actions": [
    {"action": "delete", "filename": "old.txt", "reason": "..."},
    {"action": "write", "filename": "new.py", "content": "...", "dependencies": [], "reason": "..."}
  ]
}

各 action 的字段：
- write:  {"action": "write", "filename": "相对路径", "content": "完整内容", "dependencies": ["包名"], "reason": "..."}
- delete: {"action": "delete", "filename": "相对路径", "reason": "..."}
- move:   {"action": "move", "from": "原路径", "to": "新路径", "reason": "..."}
- none:   {"action": "none", "reason": "你的回答"}

规则：
- filename / from / to 都相对于当前工作目录
- 文件在当前目录根部时直接写文件名（如 "hello.py"），不要重复目录名
- 不能是绝对路径，不能包含 ..
- dependencies 只列"项目里还没有的"第三方包
- 标准库不要列（os, sys, json, re, math 等）
- 用 pip 包名，不用 import 名（写 Pillow 不写 PIL）
"""


def chat(messages: list, cfg: dict, timeout: int = 180) -> str:
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.2,
    }
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def ask(messages: list, cfg: dict) -> dict:
    text = chat(messages, cfg)
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text)


def verify_key(cfg: dict) -> bool:
    url = cfg["base_url"].rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return True
        print(f"  ✗ 验证失败：HTTP {r.status_code}")
        return False
    except requests.RequestException as e:
        print(f"  ✗ 验证请求失败：{e}")
        return False