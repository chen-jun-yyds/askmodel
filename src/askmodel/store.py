from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Optional

from filelock import FileLock

from .models import (
    ConversationRecord,
    GlobalConfig,
    Mode,
    ProjectConfig,
    RecentEntry,
)


def home() -> Path:
    return Path(os.environ.get("ASKMODEL_HOME", Path.home() / ".askmodel")).expanduser()


class Store:
    def __init__(self, root: Optional[Path] = None):
        self.root = (root or home()).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ensure_project("default")

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def current_project_path(self) -> Path:
        return self.root / "current_project"

    @property
    def current_dir_path(self) -> Path:
        return self.root / "current_dir"

    def load_config(self) -> GlobalConfig:
        if not self.config_path.exists():
            return GlobalConfig()
        return GlobalConfig.model_validate_json(self.config_path.read_text(encoding="utf-8"))

    def save_config(self, cfg: GlobalConfig) -> None:
        self.config_path.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")

    def get_current_project(self) -> str:
        if self.current_project_path.exists():
            name = self.current_project_path.read_text(encoding="utf-8").strip()
            if name:
                return name
        return "default"

    def set_current_project(self, name: str) -> None:
        self.current_project_path.write_text(name, encoding="utf-8")

    def get_current_dir(self) -> Path:
        if self.current_dir_path.exists():
            p = Path(self.current_dir_path.read_text(encoding="utf-8").strip())
            if p.exists():
                return p
        return Path.cwd()

    def set_current_dir(self, p: Path) -> None:
        self.current_dir_path.write_text(str(p.resolve()), encoding="utf-8")

    def project_dir(self, name: Optional[str] = None) -> Path:
        name = name or self.get_current_project()
        return self.root / "projects" / name

    def list_projects(self) -> list[str]:
        d = self.root / "projects"
        if not d.exists():
            return ["default"]
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    def ensure_project(self, name: str) -> Path:
        d = self.project_dir(name)
        (d / Mode.WORK.value / "history").mkdir(parents=True, exist_ok=True)
        (d / Mode.CHAT.value / "history").mkdir(parents=True, exist_ok=True)
        (d / "backups").mkdir(parents=True, exist_ok=True)
        return d

    def delete_project(self, name: str) -> None:
        if name == "default":
            raise ValueError("default 项目不可删除")
        d = self.project_dir(name)
        if d.exists():
            shutil.rmtree(d)

    def load_project_config(self, name: Optional[str] = None) -> ProjectConfig:
        p = self.project_dir(name) / "project.json"
        if not p.exists():
            return ProjectConfig()
        return ProjectConfig.model_validate_json(p.read_text(encoding="utf-8"))

    def save_project_config(self, cfg: ProjectConfig, name: Optional[str] = None) -> None:
        d = self.ensure_project(name or self.get_current_project())
        (d / "project.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")

    # ---------- 记忆与摘要（按 mode 隔离） ----------
    def summary_path(self, mode: Mode, name: Optional[str] = None) -> Path:
        return self.project_dir(name) / mode.value / "summary.md"

    def load_summary(self, mode: Mode, name: Optional[str] = None) -> str:
        p = self.summary_path(mode, name)
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def append_summary(self, text: str, mode: Mode, name: Optional[str] = None) -> None:
        p = self.summary_path(mode, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")

    def recent_path(self, mode: Mode, name: Optional[str] = None) -> Path:
        return self.project_dir(name) / mode.value / "recent.json"

    def load_recent(self, mode: Mode, name: Optional[str] = None) -> list[RecentEntry]:
        p = self.recent_path(mode, name)
        if not p.exists():
            return []
        return [RecentEntry.model_validate(x) for x in json.loads(p.read_text(encoding="utf-8"))]

    def save_recent(self, entries: list[RecentEntry], mode: Mode, name: Optional[str] = None) -> None:
        p = self.recent_path(mode, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps([e.model_dump(mode="json") for e in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def push_recent(self, entry: RecentEntry, mode: Mode, name: Optional[str] = None) -> list[RecentEntry]:
        entries = self.load_recent(mode, name)
        entries.append(entry)
        if len(entries) > 5:
            entries = entries[-5:]
        self.save_recent(entries, mode, name)
        return entries

    def history_dir(self, mode: Mode, name: Optional[str] = None) -> Path:
        return self.project_dir(name) / mode.value / "history"

    def append_conversation(self, record: ConversationRecord, name: Optional[str] = None) -> None:
        d = self.history_dir(record.mode, name)
        d.mkdir(parents=True, exist_ok=True)
        p = d / (record.timestamp.strftime("%Y-%m-%d") + ".json")
        arr = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        arr.append(record.model_dump(mode="json"))
        p.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")

    def lock(self, name: Optional[str] = None) -> FileLock:
        d = self.ensure_project(name or self.get_current_project())
        return FileLock(str(d / ".lock"))