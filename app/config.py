"""Application settings, read from environment variables (prefix CROSSLIST_)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CROSSLIST_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'var' / 'crosslist.db'}"
    data_dir: Path = PROJECT_ROOT / "var"
    rules_dir: Path = PROJECT_ROOT / "rules"
    # Parts released within this many days are flagged as "new".
    new_part_days: int = 365
    # Load the synthetic demo dataset on startup when the database is empty.
    seed_synthetic: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
