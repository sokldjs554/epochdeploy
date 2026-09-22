from __future__ import annotations

from dataclasses import dataclass
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("EPOCHDEPLOY_DATABASE_URL", "sqlite:///./epochdeploy.db")
    jwt_secret: str = os.getenv("EPOCHDEPLOY_JWT_SECRET", "dev-only-secret")
    gitlab_webhook_token: str = os.getenv("EPOCHDEPLOY_GITLAB_WEBHOOK_TOKEN", "local-demo-token")
    executor_url: str = os.getenv("EPOCHDEPLOY_EXECUTOR_URL", "http://127.0.0.1:9080")
    executor_mode: str = os.getenv("EPOCHDEPLOY_EXECUTOR_MODE", "local")
    executor_hmac_secret: str = os.getenv("EPOCHDEPLOY_EXECUTOR_HMAC_SECRET", "local-executor-secret")
    capability_secret: str = os.getenv("EPOCHDEPLOY_CAPABILITY_SECRET", "local-capability-secret")
    upload_dir: str = os.getenv("EPOCHDEPLOY_UPLOAD_DIR", "./var/evidence")
    max_upload_bytes: int = _int("EPOCHDEPLOY_MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
    max_webhook_bytes: int = _int("EPOCHDEPLOY_MAX_WEBHOOK_BYTES", 1024 * 1024)
    demo_mode: bool = _bool("EPOCHDEPLOY_DEMO_MODE", False)


settings = Settings()
