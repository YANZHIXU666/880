from __future__ import annotations

import os
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "metadata"
DEFAULT_CONTENT_DIR = PROJECT_ROOT / "data" / "problems"


def get_data_dir(project_dir: Path | None = None) -> Path:
    env_value = os.getenv("MATH880_DATA_DIR")
    if env_value:
        return Path(env_value).expanduser()
    config_path = (project_dir or Path(__file__).resolve().parent) / "config.toml"
    if config_path.exists():
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
            value = payload.get("data", {}).get("directory")
            if value:
                path = Path(value).expanduser()
                return path if path.is_absolute() else config_path.parent / path
        except (OSError, tomllib.TOMLDecodeError):
            pass
    # GitHub's browser uploader may flatten selected folders. Keep the
    # standard data/metadata layout first, but allow a root-level packaged
    # dataset as a deployment-safe fallback.
    return DEFAULT_DATA_DIR if DEFAULT_DATA_DIR.exists() else PROJECT_ROOT


def get_content_dir(project_dir: Path | None = None) -> Path:
    env_value = os.getenv("MATH880_CONTENT_DIR")
    if env_value:
        return Path(env_value).expanduser()
    config_path = (project_dir or Path(__file__).resolve().parent) / "config.toml"
    if config_path.exists():
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
            value = payload.get("data", {}).get("content_directory")
            if value:
                path = Path(value).expanduser()
                return path if path.is_absolute() else config_path.parent / path
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return DEFAULT_CONTENT_DIR if DEFAULT_CONTENT_DIR.exists() else PROJECT_ROOT
