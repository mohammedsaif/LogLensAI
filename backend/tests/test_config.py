from app.core.config import Settings
from app.pipeline.validation import sanitize_filename


def test_list_settings_accept_comma_separated_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080, https://loglens.example.com")
    monkeypatch.setenv("ALLOWED_EXTENSIONS", ".log,.txt")
    s = Settings(_env_file=None)
    assert s.cors_origins == ["http://localhost:8080", "https://loglens.example.com"]
    assert s.allowed_extensions == [".log", ".txt"]


def test_list_settings_accept_json_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["http://a", "http://b"]')
    assert Settings(_env_file=None).cors_origins == ["http://a", "http://b"]


def test_secret_key_is_not_in_repr(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-print")
    s = Settings(_env_file=None)
    assert "sk-ant-should-not-print" not in repr(s)
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-should-not-print"


def test_sanitize_filename_strips_paths_and_odd_chars():
    assert sanitize_filename("../../etc/passwd.log") == "passwd.log"
    assert sanitize_filename("C:\\temp\\x<script>.log") == "xscript.log"
    assert sanitize_filename(None) == "upload.log"
    assert sanitize_filename("///") == "upload.log"
