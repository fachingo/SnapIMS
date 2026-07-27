from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from snapims import db
from snapims import cli
from snapims.config import DataPaths
from snapims.observability import (
    create_support_bundle,
    emit_event,
    prune_events,
    query_events,
    redact,
    redact_text,
)


def test_redaction_covers_nested_headers_urls_env_tracebacks_and_customer_pii() -> None:
    secret = "owner-secret-value"
    source = {
        "authorization": f"Bearer {secret}",
        "nested": {
            "api_key": secret,
            "url": f"https://operator:{secret}@example.test/api?token={secret}&page=2",
            "traceback": (
                "RuntimeError: request failed\n"
                f"Authorization: Bearer {secret}\n"
                f"OPENAI_API_KEY={secret}\n"
                f"curl -H 'Authorization: Bearer {secret}' https://example.test"
            ),
        },
        "customer_email": "operator@example.test",
        "notes": f"contact operator@example.test or 403-555-0199; key={secret}",
    }
    result = redact(source, known_secrets=[secret])
    rendered = json.dumps(result)
    assert secret not in rendered
    assert "operator@example.test" not in rendered
    assert "403-555-0199" not in rendered
    assert result["authorization"] == "[REDACTED]"
    assert result["customer_email"] == "[REDACTED]"
    assert "[REDACTED]" in result["nested"]["url"]
    assert "page=2" in result["nested"]["url"]


def test_redact_text_handles_multiline_cookie_and_url_credentials() -> None:
    value = (
        "Cookie: snapims_session=abc123\n"
        "https://user:password@example.test/path?csrf=unsafe&visible=yes"
    )
    result = redact_text(value)
    assert "abc123" not in result
    assert "user:password" not in result
    assert "unsafe" not in result
    assert "visible=yes" in result


def test_events_are_append_safe_queryable_and_durable_across_connections(
    tmp_path: Path,
) -> None:
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    first = emit_event(
        paths.db_file,
        component="recognition",
        event_type="recognition.started",
        operation_id="op-1",
        batch_id="BATCH-1",
        item_id="ITEM-1",
        status="RUNNING",
        detail={"image_count": 2},
        paths=paths,
    )
    second = emit_event(
        paths.db_file,
        component="recognition",
        event_type="recognition.failed",
        severity="ERROR",
        operation_id="op-1",
        batch_id="BATCH-1",
        item_id="ITEM-1",
        attempt_number=1,
        error_class="ProviderError",
        safe_summary="catalog miss",
        retry_of_event_id=first,
        detail={"authorization": "Bearer do-not-store"},
        paths=paths,
    )
    assert second > first
    events = query_events(
        paths.db_file,
        errors=True,
        batch_id="BATCH-1",
        operation_id="op-1",
    )
    assert [event["event_id"] for event in events] == [second]
    assert events[0]["detail"]["authorization"] == "[REDACTED]"
    assert events[0]["process_marker"]
    with db.connect(paths.db_file) as reopened:
        assert reopened.execute("SELECT COUNT(*) FROM operational_events").fetchone()[0] == 2
    jsonl = (paths.logs / "snapims-events.jsonl").read_text(encoding="utf-8")
    assert "do-not-store" not in jsonl
    assert "recognition.failed" in jsonl


def test_event_retention_is_bounded_by_age_and_count(tmp_path: Path) -> None:
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    with db.transaction(paths.db_file) as connection:
        for index in range(130):
            old = datetime(2020, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")
            connection.execute(
                """INSERT INTO operational_events(
                       occurred_at,severity,component,event_type,retention_class
                   ) VALUES(?,?,?,?,?)""",
                (old, "DEBUG", "test", f"old-{index}", "DEBUG"),
            )
        recent = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        for index in range(130):
            connection.execute(
                """INSERT INTO operational_events(
                       occurred_at,severity,component,event_type,retention_class
                   ) VALUES(?,?,?,?,?)""",
                (recent, "INFO", "test", f"recent-{index}", "STANDARD"),
            )
    deleted = prune_events(
        paths.db_file,
        now_at=datetime.now(UTC) + timedelta(seconds=1),
        maximum_events=100,
    )
    assert deleted == 160
    with db.connect(paths.db_file) as connection:
        assert connection.execute("SELECT COUNT(*) FROM operational_events").fetchone()[0] == 100
        assert connection.execute(
            "SELECT COUNT(*) FROM operational_events WHERE retention_class='DEBUG'"
        ).fetchone()[0] == 0


def test_support_bundle_is_bounded_redacted_and_excludes_binary_media(
    tmp_path: Path,
) -> None:
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    secret = "support-bundle-secret"
    db.set_setting(paths.db_file, "shopify_access_token", secret)
    emit_event(
        paths.db_file,
        component="shopify",
        event_type="shopify.failed",
        severity="ERROR",
        safe_summary=f"request token={secret}",
        detail={
            "customer_email": "buyer@example.test",
            "authorization": f"Bearer {secret}",
        },
        paths=paths,
        known_secrets=[secret],
    )
    media = paths.originals / "private-image.jpg"
    media.write_bytes(b"\xff\xd8PRIVATE-IMAGE-BINARY\xff\xd9")
    bundle = create_support_bundle(
        paths,
        project_path=Path(__file__).resolve().parents[1],
        health={"ok": True},
        configured_settings={"public_url": "https://example.test", "password": secret},
        known_secrets=[secret],
    )
    assert bundle.stat().st_mode & 0o777 == 0o600
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "settings.json",
            "events.json",
            "recognition-jobs.json",
            "health.json",
        }
        contents = b"\n".join(archive.read(name) for name in archive.namelist())
    assert secret.encode() not in contents
    assert b"buyer@example.test" not in contents
    assert b"PRIVATE-IMAGE-BINARY" not in contents
    assert b'"schema_version": 10' in contents


def test_log_alias_parser_accepts_composable_contract_filters() -> None:
    parser = cli.build_parser()
    arguments = [
        "--last",
        "25",
        "--since",
        "30m",
        "--errors",
        "--source",
        "recognition",
        "--batch",
        "BATCH-1",
        "--item",
        "ITEM-1",
        "--order",
        "ORDER-1",
        "--operation",
        "OP-1",
        "--json",
        "--export",
        "/tmp/events.jsonl",
    ]
    singular = parser.parse_args(["log", *arguments])
    plural = parser.parse_args(["logs", *arguments])
    assert singular.command == "log"
    assert plural.command == "logs"
    assert singular.last == plural.last == 25
    assert singular.source == plural.source == "recognition"
    assert singular.since.endswith("Z")


def test_cli_log_filters_and_export_return_only_matching_redacted_events(
    tmp_path: Path,
) -> None:
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    secret = "cli-output-secret"
    emit_event(
        paths.db_file,
        component="recognition",
        event_type="recognition.failed",
        severity="ERROR",
        operation_id="OP-1",
        batch_id="BATCH-1",
        safe_summary=f"provider token={secret}",
        known_secrets=[secret],
    )
    emit_event(
        paths.db_file,
        component="import",
        event_type="import.completed",
        operation_id="OP-2",
        batch_id="BATCH-2",
    )
    destination = tmp_path / "filtered.jsonl"
    environment = os.environ.copy()
    environment.update(
        {
            "SNAPIMS_SKIP_DOTENV": "1",
            "SNAPIMS_DATA_DIR": str(paths.root),
            "SNAPIMS_AUTH_SECRET": "",
            "SNAPIMS_ADMIN_PASSWORD_HASH": "",
            "OPENAI_API_KEY": "",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "snapims.cli",
            "--data-dir",
            str(paths.root),
            "logs",
            "--errors",
            "--source",
            "recognition",
            "--batch",
            "BATCH-1",
            "--json",
            "--export",
            str(destination),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    exported = destination.read_text(encoding="utf-8")
    assert "recognition.failed" in exported
    assert "import.completed" not in exported
    assert secret not in exported
    assert destination.stat().st_mode & 0o777 == 0o600
