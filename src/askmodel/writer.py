from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import FileOp, OpResult


class PathEscape(Exception):
    pass


def _safe_path(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if not target.is_relative_to(root_resolved):
        raise PathEscape(f"路径越界: {rel}")
    return target


def _find_nearest_match(
    lines: list[str], original: str, near_line: int
) -> Optional[tuple[int, int]]:
    orig_lines = original.split("\n")
    n = len(orig_lines)

    def find_matches(cmp) -> list[tuple[int, int]]:
        return [
            (i, i + n - 1)
            for i in range(len(lines) - n + 1)
            if all(cmp(lines[i + j], orig_lines[j]) for j in range(n))
        ]

    matches = find_matches(lambda a, b: a == b)
    if not matches:
        matches = find_matches(lambda a, b: a.strip() == b.strip())
    if not matches:
        return None

    target = max(0, near_line - 1)

    def dist(m: tuple[int, int]) -> int:
        s, e = m
        if s <= target <= e:
            return 0
        return min(abs(s - target), abs(e - target))

    matches.sort(key=lambda m: (dist(m), -m[0]))
    return matches[0]


def _backup(target: Path, backup_dir: Path) -> None:
    if not target.exists() or not target.is_file():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    bak = backup_dir / f"{ts}__{target.name}.bak"
    shutil.copy2(target, bak)

    meta_path = backup_dir / "meta.json"
    meta: dict[str, dict] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta[bak.name] = {
        "created_at": datetime.now().isoformat(),
        "last_prompted_at": None,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def execute_op(op: FileOp, root: Path, backup_dir: Path) -> OpResult:
    action = op.action

    if action == "chat":
        return OpResult(action="chat", ok=True, message=op.content or "", content=op.content)

    if not op.path:
        return OpResult(action=action, ok=False, message=f"{action} 缺少 path")

    try:
        target = _safe_path(root, op.path)
    except PathEscape as e:
        return OpResult(action=action, path=op.path, ok=False, message=str(e))

    try:
        if action == "read":
            if not target.exists():
                return OpResult(action="read", path=op.path, ok=False, message=f"没有路径：{op.path}")
            if target.is_dir():
                return OpResult(action="read", path=op.path, ok=False, message=f"是目录不是文件：{op.path}")
            text = target.read_text(encoding="utf-8", errors="replace")
            return OpResult(action="read", path=op.path, ok=True, message="ok", content=text)

        if action == "write":
            _backup(target, backup_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(op.content or "", encoding="utf-8")
            return OpResult(action="write", path=op.path, ok=True, message="ok")

        if action == "delete":
            if not target.exists():
                return OpResult(action="delete", path=op.path, ok=False, message=f"不存在：{op.path}")
            if target.is_dir():
                shutil.rmtree(target)
            else:
                _backup(target, backup_dir)
                target.unlink()
            return OpResult(action="delete", path=op.path, ok=True, message="ok")

        if action == "part_modify":
            if not target.exists() or not target.is_file():
                return OpResult(action="part_modify", path=op.path, ok=False, message=f"不是文件：{op.path}")
            if not op.original:
                return OpResult(action="part_modify", path=op.path, ok=False, message="缺少 original")
            text = target.read_text(encoding="utf-8", errors="replace")
            lines = text.split("\n")
            near = op.near_line if op.near_line is not None else 1
            found = _find_nearest_match(lines, op.original, near)
            if not found:
                return OpResult(
                    action="part_modify",
                    path=op.path,
                    ok=False,
                    message=f"在 {op.path} 中找不到匹配内容",
                )
            s, e = found
            new_lines = lines[:s] + (op.current or "").split("\n") + lines[e + 1:]
            _backup(target, backup_dir)
            target.write_text("\n".join(new_lines), encoding="utf-8")
            return OpResult(action="part_modify", path=op.path, ok=True, message="ok")

        return OpResult(action=action, path=op.path, ok=False, message=f"未知 action：{action}")
    except Exception as ex:
        return OpResult(action=action, path=op.path, ok=False, message=f"{type(ex).__name__}: {ex}")