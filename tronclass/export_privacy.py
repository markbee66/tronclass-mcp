"""Allowlisted connection settings for records intended to be shared."""
from urllib.parse import urlparse


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
        "reference_time": settings.reference_time, "student_id": settings.student_id,
        "db_path": settings.db_path.name, "prompt_path": settings.prompt_path.name,
        "connection": connection_label(settings.base_url),
    }
