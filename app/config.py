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
    # Site password: when set, every page asks for it once (cookie for 30 days).
    site_password: str = ""
    # Signs the login cookie; set a long random value in production.
    secret_key: str = ""
    # Read-only key for GET /api/inbox (the daily update run pulls the owner's comments with it). Empty: the inbox is
    # closed whenever the site has a password. Not the site password; set a long random value.
    inbox_token: str = ""
    # Load data/real/*.yaml on startup when the database has no parts (fresh server disk).
    load_real_on_start: bool = False
    # Merge data/real/unofficial/*.yaml: values read from unofficial copies of manufacturer datasheets, marked † in
    # the pages. Set CROSSLIST_USE_UNOFFICIAL_DATA=false and restart to remove every one of them from the database.
    use_unofficial_data: bool = True
    # DigiKey Product Information API (developer.digikey.com). Without these, pricing is off.
    digikey_client_id: str = ""
    digikey_client_secret: str = ""
    digikey_site: str = "US"
    digikey_currency: str = "USD"
    # Re-fetch cached prices older than this.
    price_max_age_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
