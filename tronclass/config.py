"""Settings shared by the Streamlit app and batch evaluation."""

import os
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"
DEFAULT_CLOUDFLARE_MODEL = "anthropic/claude-haiku-4.5"


def local_config() -> dict:
    """Read the explicit project config, never search parent directories for keys."""
    if not SECRETS_PATH.is_file():
        return {}
    try:
        with SECRETS_PATH.open("rb") as source:
            values = tomllib.load(source)
    except (OSError, ValueError):
        raise ValueError("無法讀取 .streamlit/secrets.toml，請確認 TOML 格式。") from None
    if any(not isinstance(values.get(section, {}), dict) for section in ("app", "cloudflare")):
        raise ValueError("本機設定的 app 與 cloudflare 必須是 TOML table。")
    return values


def cloudflare_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        value = local_config().get("cloudflare", {}).get(name, default)
    if not isinstance(value, str):
        raise ValueError(f"{name} 需為字串。")
    return value.strip()


def cloudflare_token() -> str:
    # Deliberately kept out of Settings, repr, asdict, conversation and eval logs.
    return cloudflare_value("CLOUDFLARE_API_TOKEN")


@dataclass(frozen=True)
class Settings:
    db_path: Path = ROOT / "sample_data" / "course.db"
    student_id: str = "S11200001"
    base_url: str = "http://localhost:11434/v1"
    model: str = ""
    temperature: float = 0.0
    seed: int = 42
    timeout_seconds: float = 180.0
    max_tokens: int = 2048
    reference_time: str = "2026-10-31T09:00:00+08:00"
    prompt_path: Path = ROOT / "prompts" / "system1.txt"
    provider: str = "ollama"
    cloudflare_account_id: str = ""
    cloudflare_gateway_id: str = ""

    def __post_init__(self):
        if self.provider not in {"ollama", "cloudflare"}:
            raise ValueError("LLM_PROVIDER 需為 ollama 或 cloudflare。")
        url = urlparse(self.base_url)
        if self.base_url and (url.scheme not in {"http", "https"} or not url.netloc or url.query or url.fragment or url.username or url.password):
            raise ValueError("模型網址需為 http(s) 網址，例如 http://localhost:11434/v1")
        if not self.base_url and self.provider == "ollama":
            raise ValueError("請填入 Ollama 模型網址。")
        if self.provider == "cloudflare":
            if self.cloudflare_account_id and not re.fullmatch(r"[a-fA-F0-9]{32}", self.cloudflare_account_id):
                raise ValueError("Cloudflare 帳戶 ID 需為 32 位十六進位字元。")
            if self.base_url and url.hostname not in {"api.cloudflare.com", "localhost", "127.0.0.1", "::1"}:
                raise ValueError("Cloudflare 模式僅允許官方 API 網址。")
            if url.hostname == "api.cloudflare.com" and (url.scheme != "https" or url.port not in {None, 443}):
                raise ValueError("Cloudflare 官方 API 必須使用 HTTPS。")
            if self.model and not self.model.startswith("anthropic/"):
                raise ValueError("Cloudflare Claude 模型名稱需以 anthropic/ 開頭。")
            if self.temperature > 1:
                raise ValueError("Claude 的 temperature 必須介於 0 到 1。")
        moment = datetime.fromisoformat(self.reference_time)
        if moment.tzinfo is None:
            raise ValueError("情境時間需包含時區，例如 2026-10-31T09:00:00+08:00")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature 必須介於 0 到 2。")
        if self.timeout_seconds <= 0 or self.max_tokens < 1:
            raise ValueError("逾時秒數與最大輸出 token 數必須大於零。")

    @classmethod
    def from_env(cls, provider=None):
        provider = provider or os.getenv("LLM_PROVIDER", local_config().get("app", {}).get("provider", "ollama"))
        account = cloudflare_value("CLOUDFLARE_ACCOUNT_ID") if provider == "cloudflare" else ""
        if provider == "cloudflare":
            base_url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1" if account else ""
            model = cloudflare_value("CLOUDFLARE_MODEL", DEFAULT_CLOUDFLARE_MODEL)
        else:
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
            model = os.getenv("OLLAMA_MODEL", "").strip()
        path = Path(os.getenv("TRONCLASS_DB_PATH", "sample_data/course.db")).expanduser()
        return cls(
            db_path=(ROOT / path).resolve() if not path.is_absolute() else path.resolve(),
            student_id=os.getenv("TRONCLASS_STUDENT_ID", "S11200001"),
            provider=provider,
            cloudflare_account_id=account,
            cloudflare_gateway_id=cloudflare_value("CLOUDFLARE_GATEWAY_ID") if provider == "cloudflare" else "",
            base_url=base_url,
            model=model,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            seed=int(os.getenv("LLM_SEED", "42")),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "180")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
            reference_time=os.getenv("REFERENCE_TIME", "2026-10-31T09:00:00+08:00"),
        )
