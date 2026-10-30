"""Allowlisted connection settings for records intended to be shared."""
from urllib.parse import urlparse


def redact_connection(value, base_url, api_key=""):
    """Remove connection secrets even when an upstream response echoes them."""
    host = urlparse(base_url).hostname or ""
    secrets = [api_key, base_url.rstrip("/")]
    if host not in {"localhost", "127.0.0.1", "::1"}:
        secrets.append(host)
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, dict):
        return {redact_connection(k, base_url, api_key): redact_connection(v, base_url, api_key)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_connection(v, base_url, api_key) for v in value]
    return value


def connection_label(base_url):
    if not base_url:
        return "not_configured"
    parsed = urlparse(base_url)
    scope = "local" if parsed.hostname in {"localhost", "127.0.0.1", "::1"} else "remote"
    return scope + "_" + parsed.scheme


def export_settings(settings):
    return {
        "provider": settings.provider, "model": settings.model,
        "temperature": settings.temperature, "seed": settings.seed,
        "timeout_seconds": settings.timeout_seconds, "max_tokens": settings.max_tokens,
        "thinking": settings.thinking,
        "reference_time": settings.reference_time, "student_id": settings.student_id,
        "db_path": settings.db_path.name, "prompt_path": settings.prompt_path.name,
        "connection": connection_label(settings.base_url),
    }
