import re
from pathlib import Path


def safe_path(root: Path, filename: str) -> Path:
    if filename.startswith(("/", "\\")):
        raise ValueError("不允许绝对路径")
    target = (root / filename).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("路径越界")
    return target


def show_dependencies(deps: list):
    if not deps:
        return
    valid = []
    for p in deps:
        if not re.fullmatch(r"[a-zA-Z0-9_\-\.]+", p):
            print(f"  ✗ 非法包名，已忽略: {p}")
            continue
        valid.append(p)
    if valid:
        print(f"  需要新增：{' '.join(valid)}")
        print(f"  安装命令：pip install {' '.join(valid)}")