from __future__ import annotations

from pathlib import Path

IGNORE_DIRS = {
    ".git", ".svn", ".hg",
    ".venv", "venv", "env", ".env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".tox", ".eggs",
    ".idea", ".vscode",
    ".askmodel",
}

IGNORE_FILES = {".DS_Store", "Thumbs.db"}


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def scan_tree(
    root: Path,
    max_depth: int = 5,
    max_entries: int = 500,
    max_chars: int = 20000,
) -> str:
    root = root.resolve()
    lines: list[str] = [f"{root.name}/"]
    count = 0
    truncated = False

    def walk(d: Path, prefix: str, depth: int) -> None:
        nonlocal count, truncated
        if depth > max_depth:
            lines.append(f"{prefix}... (超过最大深度 {max_depth})")
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            lines.append(f"{prefix}<无权限>")
            return
        for i, p in enumerate(entries):
            if count >= max_entries:
                truncated = True
                return
            if p.is_dir() and p.name in IGNORE_DIRS:
                continue
            if p.is_file() and p.name in IGNORE_FILES:
                continue
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            if p.is_dir():
                lines.append(f"{prefix}{connector}{p.name}/")
                walk(p, prefix + ("    " if is_last else "│   "), depth + 1)
            else:
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                lines.append(f"{prefix}{connector}{p.name} ({_fmt_size(size)})")
            count += 1
            if count >= max_entries:
                truncated = True
                return

    walk(root, "", 1)

    if truncated:
        lines.append(f"... (已截断，最多 {max_entries} 项)")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... (已截断，最多 {max_chars} 字符)"
    return text