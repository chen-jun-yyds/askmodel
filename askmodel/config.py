import json
import shutil
from datetime import datetime
from pathlib import Path

CONFIG_DIR = Path.home() / ".askmodel"
CONFIG_FILE = CONFIG_DIR / "config.json"
SMALL_FILE = CONFIG_DIR / "small.json"
PROJECTS_DIR = CONFIG_DIR / "projects"
CURRENT_PROJECT_FILE = CONFIG_DIR / "current_project"

DEFAULT_PROJECT = "default"
SCAN_SIZE_WARN = 50000

# provider 预设
PROVIDER_PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}

MAIN_DEFAULT = {
    "api_key": "",
    "base_url": "",
    "model": "",
}

SMALL_DEFAULT = {
    "api_key": "",
    "base_url": "",
    "model": "",
}


# ---------- 主模型配置 ----------

def load() -> dict:
    cfg = dict(MAIN_DEFAULT)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def is_configured(cfg: dict) -> bool:
    """三个字段都填了才算配置完成"""
    return all(str(cfg.get(k, "")).strip() for k in ("api_key", "base_url", "model"))


# ---------- 小模型配置 ----------

def load_small_raw() -> dict:
    cfg = dict(SMALL_DEFAULT)
    if SMALL_FILE.exists():
        try:
            cfg.update(json.loads(SMALL_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def load_small() -> dict:
    """小模型没配全时，回退到主模型"""
    small = load_small_raw()
    if is_configured(small):
        return small
    return load()


def save_small(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SMALL_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ---------- 项目管理 ----------

def ensure_default_project():
    (PROJECTS_DIR / DEFAULT_PROJECT).mkdir(parents=True, exist_ok=True)


def get_current_project() -> str:
    if CURRENT_PROJECT_FILE.exists():
        name = CURRENT_PROJECT_FILE.read_text(encoding="utf-8").strip()
        if name and (PROJECTS_DIR / name).is_dir():
            return name
    return DEFAULT_PROJECT


def set_current_project(name: str):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_PROJECT_FILE.write_text(name, encoding="utf-8")


def project_dir(name: str = None) -> Path:
    if name is None:
        name = get_current_project()
    d = PROJECTS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_projects() -> list:
    if not PROJECTS_DIR.exists():
        return [DEFAULT_PROJECT]
    return sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()])


def project_exists(name: str) -> bool:
    return (PROJECTS_DIR / name).is_dir()


def create_project(name: str):
    (PROJECTS_DIR / name).mkdir(parents=True, exist_ok=True)


def remove_project(name: str):
    if name == DEFAULT_PROJECT:
        raise ValueError("默认项目不能移除")
    d = PROJECTS_DIR / name
    if d.exists():
        shutil.rmtree(d)


# ---------- 扫描文件（按当前项目隔离） ----------

def scan_file() -> Path:
    return project_dir() / "scan_context.json"


def load_scan_data() -> dict:
    p = scan_file()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_scan_context() -> str:
    return load_scan_data().get("context", "")


def save_scan(context: str, paths: list):
    p = scan_file()
    p.write_text(
        json.dumps({
            "scanned_at": datetime.now().isoformat(),
            "paths": paths,
            "context": context,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def clear_scan():
    p = scan_file()
    if p.exists():
        p.unlink()