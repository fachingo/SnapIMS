from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from snapims import db
from snapims.config import DataPaths
from snapims.settings import ConfigurationError, ConfigurationService


def service_for(
    tmp_path: Path,
    *,
    environment: dict[str, str] | None = None,
    legacy_text: str = "",
) -> ConfigurationService:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    if legacy_text:
        (project / ".env").write_text(legacy_text, encoding="utf-8")
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    supplied = dict(environment or {})
    return ConfigurationService(
        project_path=project,
        paths=paths,
        process_environment=supplied,
    )


def permissions(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_precedence_and_nonsecret_provenance(tmp_path: Path) -> None:
    service = service_for(
        tmp_path,
        legacy_text=(
            "SNAPIMS_RECOGNITION_CONFIDENCE=0.70\n"
            "SNAPIMS_MOVIE_LANGUAGE=fr\n"
        ),
    )
    assert service.effective("SNAPIMS_RECOGNITION_CONFIDENCE").value == "0.70"
    assert service.effective("SNAPIMS_RECOGNITION_CONFIDENCE").provenance == "legacy .env"

    service.save_nonsecret(
        "recognition",
        {"SNAPIMS_RECOGNITION_CONFIDENCE": "0.88"},
    )
    effective = service.effective("SNAPIMS_RECOGNITION_CONFIDENCE")
    assert effective.value == "0.88"
    assert effective.provenance == "SnapIMS settings"
    assert service.effective("SNAPIMS_MOVIE_REGION").provenance == "default"

    environment_service = ConfigurationService(
        project_path=service.project_path,
        paths=service.paths,
        process_environment={"SNAPIMS_RECOGNITION_CONFIDENCE": "0.92"},
    )
    effective = environment_service.effective("SNAPIMS_RECOGNITION_CONFIDENCE")
    assert effective.value == "0.92"
    assert effective.provenance == "environment"
    assert effective.externally_managed


def test_environment_override_is_never_overwritten(tmp_path: Path) -> None:
    service = service_for(
        tmp_path,
        environment={"SNAPIMS_MOVIE_LANGUAGE": "de"},
    )
    with pytest.raises(ConfigurationError, match="process environment"):
        service.save_nonsecret("movie", {"SNAPIMS_MOVIE_LANGUAGE": "en"})
    assert service.value("SNAPIMS_MOVIE_LANGUAGE") == "de"


def test_secret_store_is_atomic_masked_and_owner_only(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    first = "sk-test-value-one"
    revision = service.save_secrets("recognition", {"OPENAI_API_KEY": first})

    assert service.value("OPENAI_API_KEY") == first
    model = service.read_model("recognition")["OPENAI_API_KEY"]
    assert model.display_value == "••••••••"
    assert first not in model.display_value
    assert permissions(service.paths.secrets) == 0o700
    assert permissions(service.secret_backup_dir) == 0o700
    assert permissions(service.secret_file) == 0o600
    assert not list(service.paths.secrets.glob("*.tmp"))

    raw_revision = db.connect(service.paths.db_file)
    try:
        row = raw_revision.execute(
            "SELECT * FROM configuration_revisions WHERE revision_id=?",
            (revision,),
        ).fetchone()
    finally:
        raw_revision.close()
    assert row is not None
    assert json.loads(row["changed_fields_json"]) == ["OPENAI_API_KEY"]
    assert row["previous_values_json"] == "{}"
    assert row["new_values_json"] == "{}"
    assert first not in json.dumps(dict(row))


def test_secret_replacement_has_recoverable_backup(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    service.save_secrets("recognition", {"OPENAI_API_KEY": "sk-first"})
    second_revision = service.save_secrets(
        "recognition",
        {"OPENAI_API_KEY": "sk-second"},
    )
    revisions = {row["revision_id"]: row for row in service.revisions()}
    backup_name = revisions[second_revision]["backup_reference"]

    assert backup_name
    backup_path = service.secret_backup_dir / backup_name
    assert permissions(backup_path) == 0o600
    service.rollback_secret_file(backup_name, section="recognition")
    assert service.value("OPENAI_API_KEY") == "sk-first"


def test_insecure_secret_store_permissions_are_refused(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    service.save_secrets("recognition", {"OPENAI_API_KEY": "sk-protected"})
    service.secret_file.chmod(0o644)

    with pytest.raises(ConfigurationError, match="0600"):
        service.value("OPENAI_API_KEY")


def test_legacy_secret_migration_copies_without_deleting_env_file(tmp_path: Path) -> None:
    legacy_value = "sk-legacy-only"
    service = service_for(
        tmp_path,
        legacy_text=f"OPENAI_API_KEY={legacy_value}\n",
    )
    assert service.legacy_secret_fields() == ("OPENAI_API_KEY",)

    service.migrate_legacy_secrets(["OPENAI_API_KEY"])

    assert service.secret_file.is_file()
    assert service.value("OPENAI_API_KEY") == legacy_value
    assert (service.project_path / ".env").read_text(encoding="utf-8") == (
        f"OPENAI_API_KEY={legacy_value}\n"
    )


def test_only_probed_models_can_be_assigned_to_recognition_roles(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    with pytest.raises(ConfigurationError, match="must pass"):
        service.save_nonsecret(
            "recognition",
            {"SNAPIMS_OPENAI_BASELINE_MODEL": "gpt-example"},
        )

    service.save_model_capability(
        model_id="gpt-example",
        supports_images=True,
        supports_strict_schema=True,
        status="PASS",
    )
    service.save_nonsecret(
        "recognition",
        {"SNAPIMS_OPENAI_BASELINE_MODEL": "gpt-example"},
    )
    assert service.value("SNAPIMS_OPENAI_BASELINE_MODEL") == "gpt-example"


def test_current_manifest_contains_configuration_contract(data_paths: DataPaths) -> None:
    db.initialize(data_paths.db_file, paths=data_paths)
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        report = db.schema_manifest_report(connection)
    assert report["ok"], report
