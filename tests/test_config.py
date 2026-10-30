import json
from dataclasses import asdict

import pytest

from tronclass.config import Settings, cloudflare_token


def test_local_cloudflare_config_loads_without_putting_token_in_settings(tmp_path, monkeypatch):
    import tronclass.config
    path = tmp_path / "secrets.toml"
    path.write_text('[app]\nprovider="cloudflare"\n[cloudflare]\n'
                    'CLOUDFLARE_ACCOUNT_ID="0123456789abcdef0123456789abcdef"\n'
                    'CLOUDFLARE_API_TOKEN="fake-local-token"\n'
                    'CLOUDFLARE_MODEL="anthropic/fixture"\n', encoding="utf-8")
    monkeypatch.setattr(tronclass.config, "SECRETS_PATH", path)
    settings = Settings.from_env()
    assert settings.provider == "cloudflare"
    assert settings.base_url == "https://api.cloudflare.com/client/v4/accounts/0123456789abcdef0123456789abcdef/ai/v1"
    assert settings.model == "anthropic/fixture"
    assert cloudflare_token() == "fake-local-token"
    assert "fake-local-token" not in repr(settings)
    assert "fake-local-token" not in json.dumps(asdict(settings), default=str)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fake-environment-token")
    assert cloudflare_token() == "fake-environment-token"
    assert Settings.from_env(provider="ollama").base_url == "http://localhost:11434/v1"


@pytest.mark.parametrize("base_url", ["https://example.com/v1", "http://api.cloudflare.com/v1", "https://api.cloudflare.com:8443/v1"])
def test_cloudflare_credentials_cannot_be_sent_to_arbitrary_hosts(base_url):
    with pytest.raises(ValueError):
        Settings(provider="cloudflare", base_url=base_url, model="anthropic/fixture")
