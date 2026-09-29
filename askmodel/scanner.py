import os
from pathlib import Path

# 目录黑名单（精确匹配）
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".idea", ".vscode", ".next",
    "AppData", ".cache", ".npm", ".cargo", ".rustup",
    "site-packages",
}

# 文件白名单（只有这些后缀才读内容）
IMPORTANT_EXTS = {
    ".py", ".c", ".cpp", ".h", ".hpp", ".js", ".ts", ".java",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".toml", ".json", ".yaml", ".yml", ".ini", ".cfg",
    ".md", ".rst", ".txt",
    ".html", ".htm", ".css", ".scss", ".less",   # 新增
}

# 标准模式的限制
MAX_DEPTH = 6
MAX_FILES = 500
MAX_FILE_CHARS = 1500
MAX_SAMPLE_FILES = 40


def _is_ignored_dir(name: str) -> bool:
    if name in IGNORE_DIRS:
        return True
    if name.startswith("."):
        return True
    if name.endswith(".egg-info"):
        return True
    if name.endswith(".dist-info"):
        return True
    return False


def scan_paths(paths_with_deep: list) -> str:
    """paths_with_deep: [(path, deep), ...]"""
    parts = []
    for p, deep in paths_with_deep:
        path = Path(p).resolve()
        if not path.exists():
            parts.append(f"## {p}\n(路径不存在)")
            continue
        if path.is_file():
            parts.append(_scan_file(path, deep))
        elif path.is_dir():
            parts.append(_scan_dir(path, deep))
    return "\n\n".join(parts)


def _scan_file(path: Path, deep: bool) -> str:
    if path.suffix not in IMPORTANT_EXTS:
        return f"## 文件: {path.name}\n(后缀不在白名单，已跳过)"
    try:
        content = path.read_text(encoding="utf-8")
        if not deep and len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + "\n...(截断)"
        return f"## 文件: {path.name}\n```\n{content}\n```"
    except Exception as e:
        return f"## 文件: {path.name}\n(无法读取: {e})"


def _scan_dir(root: Path, deep: bool) -> str:
    tree, sampled = [], []
    file_count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_ignored_dir(d)]

        dp = Path(dirpath)
        rel_dir = dp.relative_to(root)
        if len(rel_dir.parts) > MAX_DEPTH:
            dirnames[:] = []
            continue

        indent = "  " * len(rel_dir.parts)
        if rel_dir.parts:
            tree.append(f"{indent}{dp.name}/")

        for f in sorted(filenames):
            if f.startswith("."):
                continue

            fp = dp / f
            if fp.suffix not in IMPORTANT_EXTS:
                continue

            file_count += 1
            if not deep and file_count > MAX_FILES:
                tree.append(f"{indent}  ...(超过 {MAX_FILES} 文件，截断)")
                break

            try:
                size = fp.stat().st_size
            except OSError:
                continue
            tree.append(f"{indent}  {f} ({size}B)")

            if deep or len(sampled) < MAX_SAMPLE_FILES:
                try:
                    content = fp.read_text(encoding="utf-8")
                    if not deep and len(content) > MAX_FILE_CHARS:
                        content = content[:MAX_FILE_CHARS] + "\n...(截断)"
                    rel = fp.relative_to(root)
                    sampled.append(f"### {rel}\n```\n{content}\n```")
                except Exception:
                    pass

        if not deep and file_count > MAX_FILES:
            break

    result = f"## 目录: {root.name}\n\n目录结构：\n" + "\n".join(tree)
    if sampled:
        result += "\n\n关键文件内容：\n" + "\n\n".join(sampled)
    return result