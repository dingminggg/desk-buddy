import json
import os
from pathlib import Path

from pydantic import BaseModel


class Config(BaseModel):
    provider: str = "openai_compatible"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    roam_enabled: bool = True
    sound_enabled: bool = True
    sound_file: str = ""  # 自定义提示音（mp3/wav 绝对路径）；留空用默认叮声
    character: str = "default"

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)


def default_config_path() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "desk-buddy" / "config.json"


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(**data)


def save_config(config: Config, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
