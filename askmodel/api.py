import json
import requests

SYSTEM_PROMPT = """你是代码生成助手。我会给你项目理解摘要、历史记忆和最近对话。
严格模仿现有风格生成代码。

只返回 JSON，不要解释：
{
  "filename": "相对路径",
  "content": "完整文件内容",
  "dependencies": ["需要新增的第三方包"],
  "reason": "一句话理由"
}

filename 规则：
- 相对于当前工作目录
- 如果文件放当前目录根部，直接写文件名（如 "hello.py"），不要重复目录名，不要加前缀
- 不能是绝对路径，不能包含 ..

dependencies 规则：
- 只列"项目里还没有的"第三方包
- 先检查扫描文本中的 requirements.txt / pyproject.toml / 现有代码的 import
- 已经在项目里的不要列
- 标准库不要列（os, sys, json, re, math 等）
- 用 pip 包名，不要用 import 名

如果用户只是问问题不需要写文件，返回：
{
  "filename": "",
  "content": "",
  "dependencies": [],
  "reason": "你的回答"
}
"""


def chat(messages: list, cfg: dict, timeout: int = 180) -> str:
    """通用调用：返回模型的纯文本回复"""
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
    """结构化调用：要求模型返回 JSON"""
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
        if r.status_code == 401:
            print("     API Key 无效或已过期")
        elif r.status_code == 403:
            print("     API Key 无权限")
        return False
    except requests.RequestException as e:
        print(f"  ✗ 验证请求失败：{e}")
        return False