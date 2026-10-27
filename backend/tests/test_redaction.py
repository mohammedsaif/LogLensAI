"""Privacy: secrets and personal data never reach the model prompt."""

import pytest

from app.ai.prompts.v1 import build_user_prompt
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.redaction import redact
from tests.conftest import make_settings


@pytest.mark.parametrize(
    "text,secret,category",
    [
        ("contact bob.smith@example.com now", "bob.smith@example.com", "email"),
        ("Authorization: Bearer abcDEF123456ghiJKL789", "abcDEF123456ghiJKL789", "bearer_token"),
        ("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl here", "eyJhbGciOiJIUzI1NiJ9", "jwt"),
        ("key sk-ant-api03-ABCDEFGHIJKLMNOPQRST used", "sk-ant-api03-ABCDEFGHIJKLMNOPQRST", "api_key"),
        ("aws AKIAIOSFODNN7EXAMPLE leaked", "AKIAIOSFODNN7EXAMPLE", "api_key"),
        ("github pat ghp_abcdefghijklmnopqrstuvwxyz0123456789", "ghp_abcdefghijklmnopqrstuvwxyz0123456789", "api_key"),
        ("login password=hunter2 ok", "hunter2", "secret_assignment"),
        ('{"client_secret": "s3cr3t-value"}', "s3cr3t-value", "secret_assignment"),
        ("api_key: live_abc123", "live_abc123", "secret_assignment"),
        ("db postgres://app:s3cretPass@db.internal:5432/shop", "s3cretPass", "url_credentials"),
        ("card 4111 1111 1111 1111 charged", "4111 1111 1111 1111", "card_number"),
        ("from 192.168.1.20 port", "192.168.1.20", "ip_address"),
        ("-----BEGIN RSA PRIVATE KEY-----MIIEow-----END RSA PRIVATE KEY-----", "MIIEow", "private_key"),
    ],
)
def test_redacts_common_secret_formats(text, secret, category):
    out, counts = redact(text)
    assert secret not in out
    assert counts.get(category, 0) >= 1


def test_non_secret_numbers_and_ids_are_kept():
    text = "order 1234567890123 failed after 5000ms req-1a2b3c4d uuid 123e4567-e89b-12d3-a456-426614174000"
    out, counts = redact(text)
    assert "1234567890123" in out  # fails Luhn -> not a card
    assert "req-1a2b3c4d" in out and "123e4567-e89b-12d3-a456-426614174000" in out
    assert "card_number" not in counts


def test_ip_redaction_can_be_disabled():
    out, _ = redact("from 10.1.2.3", redact_ips=False)
    assert "10.1.2.3" in out


def test_prompt_contains_no_secrets_end_to_end():
    log = "\n".join(
        [
            "2026-01-01T00:00:01Z ERROR [pay] Provider auth rejected api_key=sk-live-FAKEFAKEFAKEFAKE1234 password=hunter2",
            "2026-01-01T00:00:02Z CRITICAL [auth] Lockout for admin@example.com from 203.0.113.9",
            "2026-01-01T00:00:03Z ERROR [api] Forwarded Authorization: Bearer abcDEF123456ghiJKL789mno",
            "2026-01-01T00:00:04Z ERROR [db] connect postgres://u:p4ssw0rd@db:5432/x failed: connection refused",
        ]
    )
    result = run_pipeline(log, make_settings())
    prompt = build_user_prompt(result.evidence)
    for secret in [
        "sk-live-FAKE",
        "hunter2",
        "admin@example.com",
        "203.0.113.9",
        "abcDEF123456ghiJKL789mno",
        "p4ssw0rd",
    ]:
        assert secret not in prompt
    assert "[REDACTED_" in prompt
    assert result.evidence.redaction_counts  # reported to the UI
