import re
import shutil
from pathlib import Path


def safe_path(root: Path, filename: str) -> Path:
    if filename.startswith(("/", "\\")):
        raise ValueError("不允许绝对路径")
    target = (root / filename).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("路径越界")
    return target


def _check_protected(p: Path):
    """禁止操作受保护的目录"""
    for part in p.parts:
        if part in (".git", ".askmodel"):
            raise ValueError(f"不能操作受保护目录：{part}")


def do_write(root: Path, filename: str, content: str):
    target = safe_path(root, filename)
    _check_protected(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def do_delete(root: Path, filename: str):
    target = safe_path(root, filename)
    _check_protected(target)
    if target == root:
        raise ValueError("不能删除项目根目录")
    if not target.exists():
        raise FileNotFoundError(f"路径不存在：{target}")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return target


def do_move(root: Path, src_name: str, dst_name: str):
    src = safe_path(root, src_name)
    dst = safe_path(root, dst_name)
    _check_protected(src)
    _check_protected(dst)
    if not src.exists():
        raise FileNotFoundError(f"源路径不存在：{src}")
    if src == root:
        raise ValueError("不能移动项目根目录")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    shutil.move(str(src), str(dst))
    return src, dst


def count_files(target: Path) -> int:
    """统计目录下的文件数（不递归进 .git）"""
    if target.is_file():
        return 1
    n = 0
    for p in target.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            n += 1
    return n


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