from datetime import UTC, datetime

import pytest

from app.pipeline.normalize import make_fingerprint, make_template, normalize_severity, parse_timestamp
from app.pipeline.parser import parse_line, parse_text


def test_iso_text_line_with_bracketed_service_and_correlation():
    rec = parse_line(7, "2026-03-14T09:02:29.232Z WARN  [order-service] Pool at 95% correlation_id=req-1a2b3c4d")
    assert rec.line_no == 7
    assert rec.ts == datetime(2026, 3, 14, 9, 2, 29, 232000, tzinfo=UTC)
    assert rec.severity == "WARN"
    assert rec.service == "order-service"
    assert rec.message.startswith("Pool at 95%")
    assert rec.correlation_id == "req-1a2b3c4d"
    assert rec.parse_ok and rec.fmt == "text"


def test_python_logging_format_with_comma_millis_and_dash_service():
    rec = parse_line(1, "2026-05-02 08:00:01,120 ERROR checkout-api - Payment failed")
    assert rec.ts == datetime(2026, 5, 2, 8, 0, 1, 120000, tzinfo=UTC)
    assert rec.severity == "ERROR"
    assert rec.service == "checkout-api"
    assert rec.message == "Payment failed"


def test_syslog_format_uses_default_year_and_host_service():
    rec = parse_line(1, "May  2 08:00:03 web-01 nginx[2211]: upstream timed out", default_year=2026)
    assert rec.ts == datetime(2026, 5, 2, 8, 0, 3, tzinfo=UTC)
    assert rec.service == "nginx"
    assert rec.message == "upstream timed out"


def test_timezone_offset_is_normalized_to_utc():
    rec = parse_line(1, "2026-01-01T10:00:00+0200 INFO [a.b] hi")
    assert rec.ts == datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "line,severity,service,message",
    [
        ('{"timestamp":"2026-05-02T08:00:04.5Z","level":"info","service":"cart","message":"ok"}', "INFO", "cart", "ok"),
        ('{"ts":1777708805,"lvl":40,"logger":"cart","msg":"Disk 91%"}', "WARN", "cart", "Disk 91%"),
        (
            '{"@timestamp":"2026-05-02T08:00:04Z","log.level":"error","service":{"name":"api"},"message":"x"}',
            "ERROR",
            "api",
            "x",
        ),
        ('{"time":"2026-05-02T08:00:04Z","severity":"FATAL","app":"pay","msg":"down"}', "CRITICAL", "pay", "down"),
    ],
)
def test_json_lines(line, severity, service, message):
    rec = parse_line(1, line)
    assert rec.fmt == "json"
    assert rec.severity == severity
    assert rec.service == service
    assert rec.message == message
    assert rec.ts is not None


def test_json_epoch_millis_and_request_id():
    rec = parse_line(1, '{"ts":1777708805000,"level":"warn","msg":"m","request_id":"r-99"}')
    assert rec.ts == datetime.fromtimestamp(1777708805, UTC)
    assert rec.correlation_id == "r-99"


def test_json_without_message_keeps_other_fields():
    rec = parse_line(1, '{"level":"error","code":42}')
    assert rec.severity == "ERROR"
    assert '"code": 42' in rec.message


def test_malformed_lines_are_preserved_and_flagged():
    records = parse_text("2026-01-01T00:00:00Z INFO [svc] ok\nthis is garbage\n{broken json\n")
    assert [r.parse_ok for r in records] == [True, False, False]
    assert records[1].raw == "this is garbage"
    assert records[2].fmt == "unparsed"


def test_stack_trace_lines_are_continuations_of_previous_event():
    text = (
        "2026-01-01T00:00:00Z ERROR [api] Unhandled exception\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in f\n'
        "ValueError: boom\n"
        "    at com.example.Foo.bar(Foo.java:10)\n"
    )
    records = parse_text(text)
    assert not records[0].is_continuation
    assert all(r.is_continuation for r in records[1:])
    assert all(r.severity == "ERROR" and r.service == "api" for r in records[1:])


def test_blank_lines_keep_line_numbers():
    records = parse_text("a INFO x\n\n2026-01-01T00:00:00Z ERROR [s] y\n")
    assert [r.line_no for r in records] == [1, 2, 3]
    assert records[1].fmt == "blank"
    assert records[2].severity == "ERROR"


def test_lowercase_error_word_in_message_does_not_set_severity_without_position():
    rec = parse_line(1, "2026-01-01T00:00:00Z [svc] retrying after error in worker")
    assert rec.severity == "UNKNOWN"
    assert rec.parse_ok  # timestamp present


def test_capitalized_word_before_colon_is_not_a_service():
    rec = parse_line(1, "2026-01-01T00:00:00Z ERROR Connection: refused by peer")
    assert rec.service is None
    assert rec.message == "Connection: refused by peer"


def test_very_long_lines_are_truncated_but_kept():
    rec = parse_line(1, "2026-01-01T00:00:00Z INFO " + "x" * 20000)
    assert len(rec.raw) < 10100 and rec.raw.endswith("[truncated]")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("warning", "WARN"),
        ("ERR", "ERROR"),
        ("fatal", "CRITICAL"),
        ("notice", "INFO"),
        (50, "ERROR"),
        (10, "DEBUG"),
        ("x", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_normalize_severity(value, expected):
    assert normalize_severity(value) == expected


def test_parse_timestamp_invalid_returns_none():
    assert parse_timestamp("not a time") is None
    assert parse_timestamp("2026-13-45T00:00:00Z") is None
    assert parse_timestamp(True) is None


def test_template_masks_variable_parts():
    a = make_template(
        "Query timed out after 5000ms id=abc123 from 10.0.0.1:5432 user bob@x.com uuid 123e4567-e89b-12d3-a456-426614174000"
    )
    b = make_template(
        "Query timed out after 120ms id=zzz999 from 10.0.0.2:5432 user amy@y.org uuid 223e4567-e89b-12d3-a456-426614174000"
    )
    assert a == b
    assert "<n>ms" in a and "<ip>" in a and "<email>" in a and "<uuid>" in a


def test_fingerprint_depends_on_severity_and_service():
    t = "Pool usage reached <n>%"
    assert make_fingerprint("WARN", "a", t) != make_fingerprint("ERROR", "a", t)
    assert make_fingerprint("WARN", "a", t) != make_fingerprint("WARN", "b", t)
    assert make_fingerprint("WARN", "a", t) == make_fingerprint("WARN", "a", t)


def test_identifier_values_without_digits_are_masked():
    # Regression: hex correlation IDs made only of letters used to create one-off groups.
    a = make_template("Query timed out correlation_id=req-abcdefab")
    b = make_template("Query timed out correlation_id=req-0a1b2c3d")
    c = make_template("Query timed out request_id=ZZZZ")
    assert a == b
    assert c.endswith("request_id=<id>")
    assert make_template("query=select_order_items level=warn") == "query=select_order_items level=warn"
