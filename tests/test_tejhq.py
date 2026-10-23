import hashlib
import json
import urllib.error
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nse_swing_agent.cli import main
from nse_swing_agent.historical_data import load_historical_file
from nse_swing_agent.tejhq import TejHQClient, TejHQError, _validate_response, fetch_history


def response_body(rows=None, **meta_overrides):
    rows = rows or [
        {
            "date": "2025-01-03",
            "open": 10,
            "high": 12,
            "low": 9,
            "close": 11,
            "volume": 20,
            "last": 10.9,
            "prev_close": 10.5,
            "turnover": 220,
            "trades": 8,
        },
        {"date": "2025-01-02", "open": 9, "high": 11, "low": 8, "close": 10, "volume": 10},
    ]
    meta = {
        "exchange": "NSE",
        "symbol": "RELIANCE",
        "from": "2025-01-02",
        "to": "2025-01-03",
        "count": len(rows),
    }
    meta.update(meta_overrides)
    return json.dumps({"data": rows, "meta": meta}, separators=(",", ":")).encode()


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size=-1):
        return self.body[:size]


def test_tejhq_fetch_saves_identical_raw_normalizes_validates_and_writes_manifest(tmp_path: Path):
    raw = response_body()
    client = TejHQClient(opener=lambda request, timeout: FakeResponse(raw), sleep=lambda _: None)
    result = fetch_history(
        "reliance",
        date(2025, 1, 2),
        date(2025, 1, 3),
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        client=client,
    )
    assert result.raw_path.read_bytes() == raw
    assert result.raw_sha256 == hashlib.sha256(raw).hexdigest()
    rows = load_historical_file(result.normalized_path)
    assert [row.session_date for row in rows] == [date(2025, 1, 2), date(2025, 1, 3)]
    assert all(row.adjustment_policy == "raw_unadjusted" for row in rows)
    manifest = json.loads(result.provenance_path.read_text())
    assert manifest["actual_date_range"] == ["2025-01-02", "2025-01-03"]
    assert manifest["raw_file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["schema_version"] == "1.0"
    assert manifest["adjustment_status"].startswith("raw_unadjusted")


def test_provider_retries_transient_http_and_uses_explicit_timeout():
    calls, pauses = [], []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)
        return FakeResponse(response_body())

    client = TejHQClient(timeout=4, retries=1, opener=opener, sleep=pauses.append)
    endpoint, body = client.fetch_bytes("RELIANCE", date(2025, 1, 2), date(2025, 1, 3))
    assert len(body) > 0 and "from=2025-01-02" in endpoint
    assert calls == [(endpoint, 4), (endpoint, 4)]
    assert pauses == [0.25]


def test_provider_reports_http_error_without_retrying_client_error():
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, None)

    client = TejHQClient(retries=3, opener=opener, sleep=lambda _: pytest.fail("unexpected retry"))
    with pytest.raises(TejHQError, match="HTTP 403"):
        client.fetch_bytes("RELIANCE", date(2025, 1, 2), date(2025, 1, 3))


@pytest.mark.parametrize(
    "rows, metadata, error",
    [
        ([{"date": "2025-01-02", "open": 1, "high": 1, "low": 1, "close": 1}], {}, "volume"),
        (
            [{"date": "bad", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}],
            {},
            "invalid date",
        ),
        (
            [{"date": "2025-01-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": -1}],
            {},
            "volume",
        ),
        (
            [{"date": "2025-01-02", "open": 12, "high": 11, "low": 9, "close": 10, "volume": 1}],
            {},
            "canonical validation",
        ),
    ],
)
def test_invalid_provider_rows_are_rejected(tmp_path, rows, metadata, error):
    body = response_body(rows, **metadata)
    client = TejHQClient(opener=lambda request, timeout: FakeResponse(body))
    if "canonical" in error:
        with pytest.raises(TejHQError, match=error):
            fetch_history(
                "RELIANCE",
                date(2025, 1, 2),
                date(2025, 1, 3),
                raw_dir=tmp_path / "raw",
                processed_dir=tmp_path / "out",
                client=client,
            )
        assert not list((tmp_path / "out").glob("*.csv"))
        assert list((tmp_path / "raw").glob("*.json"))
    else:
        with pytest.raises(TejHQError, match=error):
            _validate_response(body, "RELIANCE", date(2025, 1, 2), date(2025, 1, 3))


def test_duplicate_dates_and_bad_metadata_rejected():
    duplicate = [
        {"date": "2025-01-02", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
        {"date": "2025-01-02", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
    ]
    with pytest.raises(TejHQError, match="duplicate session"):
        _validate_response(response_body(duplicate), "RELIANCE", date(2025, 1, 2), date(2025, 1, 3))
    with pytest.raises(TejHQError, match="does not match"):
        _validate_response(
            response_body(symbol="OTHER"), "RELIANCE", date(2025, 1, 2), date(2025, 1, 3)
        )


def test_raw_response_is_never_overwritten(tmp_path, monkeypatch):
    raw = response_body()
    client = TejHQClient(opener=lambda request, timeout: FakeResponse(raw))
    import nse_swing_agent.tejhq as provider

    class FrozenDateTime:
        @staticmethod
        def now(tz):
            return datetime(2025, 1, 5, tzinfo=UTC)

    monkeypatch.setattr(provider, "datetime", FrozenDateTime)
    fetch_history(
        "RELIANCE",
        date(2025, 1, 2),
        date(2025, 1, 3),
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "out",
        client=client,
    )
    with pytest.raises(TejHQError, match="refusing to overwrite"):
        fetch_history(
            "RELIANCE",
            date(2025, 1, 2),
            date(2025, 1, 3),
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "out",
            client=client,
        )


def test_fetch_cli_requires_explicit_symbol_and_reports_network_errors(
    tmp_path, monkeypatch, capsys
):
    import nse_swing_agent.tejhq as provider

    def offline(request, timeout):
        raise urllib.error.URLError("offline test")

    monkeypatch.setattr(provider.urllib.request, "urlopen", offline)
    code = main(
        [
            "fetch-history",
            "--symbol",
            "RELIANCE",
            "--from",
            "2025-01-02",
            "--to",
            "2025-01-03",
            "--raw-dir",
            str(tmp_path / "raw"),
            "--processed-dir",
            str(tmp_path / "out"),
            "--retries",
            "0",
        ]
    )
    assert code == 2  # offline/network failure is reported; CLI does not conceal it.
    assert "offline test" in capsys.readouterr().err
