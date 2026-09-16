import pytest

from printful_core import auth
from printful_core.errors import PrintfulAuthError


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.delenv("PRINTFUL_API_KEY", raising=False)
    monkeypatch.delenv("PRINTFUL_STORE_ID", raising=False)
    monkeypatch.setattr(auth, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(auth, "CONFIG_FILE", tmp_path / "config.json")


def test_explicit_key_beats_environment(monkeypatch):
    monkeypatch.setenv("PRINTFUL_API_KEY", "from-env")
    assert auth.Credentials.resolve(api_key="explicit").api_key == "explicit"


def test_environment_beats_config(monkeypatch):
    auth.save_config({"api_key": "from-config"})
    monkeypatch.setenv("PRINTFUL_API_KEY", "from-env")
    assert auth.Credentials.resolve().api_key == "from-env"


def test_config_used_when_nothing_else_set():
    auth.save_config({"api_key": "from-config"})
    assert auth.Credentials.resolve().api_key == "from-config"


def test_missing_key_raises_with_instructions():
    with pytest.raises(PrintfulAuthError, match="printful.com/dashboard/api"):
        auth.Credentials.resolve()


def test_headers_always_carry_bearer_token():
    creds = auth.Credentials(api_key="tok", store_id=None)
    assert creds.headers()["Authorization"] == "Bearer tok"
    assert creds.headers()["Content-Type"] == "application/json"


def test_store_header_present_only_when_set():
    assert "X-PF-Store-Id" not in auth.Credentials("tok", None).headers()
    assert auth.Credentials("tok", "42").headers()["X-PF-Store-Id"] == "42"


def test_store_id_coerced_to_string():
    assert auth.Credentials.resolve(api_key="t", store_id=42).store_id == "42"


def test_config_round_trip():
    auth.save_config({"api_key": "k", "store_id": "9"})
    assert auth.load_config() == {"api_key": "k", "store_id": "9"}


def test_corrupt_config_reads_as_empty():
    auth.CONFIG_FILE.write_text("{not json")
    assert auth.load_config() == {}
