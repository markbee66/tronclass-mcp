import pytest


@pytest.fixture(autouse=True)
def isolate_local_cloud_credentials(monkeypatch, tmp_path):
    """Tests never read or forward the person's real cloud credentials."""
    import tronclass.config
    monkeypatch.setattr(tronclass.config, "SECRETS_PATH", tmp_path / "no-secrets.toml")
    for name in ("LLM_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
                 "CLOUDFLARE_MODEL", "CLOUDFLARE_GATEWAY_ID"):
        monkeypatch.delenv(name, raising=False)
