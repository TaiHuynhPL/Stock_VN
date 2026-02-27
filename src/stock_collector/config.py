"""Application configuration loader."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "postgres"
    user: str = ""
    password: str = ""
    host_ipv4: str = ""  # Optional IPv4 override for Docker IPv6 issues
    pooler_url: str = ""  # Full pooler connection string (from Supabase dashboard)

    @property
    def url(self) -> str:
        """Build SQLAlchemy database URL."""
        from urllib.parse import quote_plus
        pwd = quote_plus(self.password)
        conn_host = self.host_ipv4 or self.host
        return f"postgresql://{self.user}:{pwd}@{conn_host}:{self.port}/{self.name}"


@dataclass
class CollectionConfig:
    default_start_date: str = "2012-01-01"
    batch_size: int = 50
    request_delay: float = 0.5
    max_retries: int = 3
    retry_delay: float = 5.0
    rate_limit_delay: float = 60.0


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    file: str = "logs/stock_collector.log"


@dataclass
class AppConfig:
    db: DBConfig = field(default_factory=DBConfig)
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    indices: list[str] = field(default_factory=lambda: ["VNINDEX", "HNX-INDEX", "UPCOM-INDEX"])
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _find_project_root() -> Path:
    """Find project root by looking for config.yaml or pyproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "config.yaml").exists() or (parent / "pyproject.toml").exists():
            return parent
    return current


def load_config() -> AppConfig:
    """Load configuration from .env and config.yaml."""
    project_root = _find_project_root()

    # Load .env file
    env_path = project_root / ".env"
    load_dotenv(env_path)

    # Load config.yaml
    config_path = project_root / "config.yaml"
    yaml_config: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            yaml_config = yaml.safe_load(f) or {}

    # Build DB config from environment
    db_config = DBConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        name=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        host_ipv4=os.getenv("DB_HOST_IPV4", ""),
        pooler_url=os.getenv("DB_POOLER_URL", ""),  # Supabase pooler connection string
    )

    # Build collection config
    coll_data = yaml_config.get("collection", {})
    collection_config = CollectionConfig(
        default_start_date=coll_data.get("default_start_date", "2012-01-01"),
        batch_size=coll_data.get("batch_size", 50),
        request_delay=coll_data.get("request_delay", 0.5),
        max_retries=coll_data.get("max_retries", 3),
        retry_delay=coll_data.get("retry_delay", 5.0),
        rate_limit_delay=coll_data.get("rate_limit_delay", 60.0),
    )

    # Set VNSTOCK_API_KEY so vnstock picks it up automatically
    api_key = os.getenv("VNSTOCK_API_KEY", "")
    if api_key:
        os.environ["VNSTOCK_API_KEY"] = api_key

    # Build logging config
    log_data = yaml_config.get("logging", {})
    logging_config = LoggingConfig(
        level=log_data.get("level", "INFO"),
        format=log_data.get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"),
        file=log_data.get("file", "logs/stock_collector.log"),
    )

    return AppConfig(
        db=db_config,
        collection=collection_config,
        indices=yaml_config.get("indices", ["VNINDEX", "HNX-INDEX", "UPCOM-INDEX"]),
        logging=logging_config,
    )
