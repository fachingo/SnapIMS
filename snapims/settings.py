from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from dotenv import dotenv_values


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SettingDefinition:
    key: str
    section: str
    default: str = ""
    secret: bool = False
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EffectiveSetting:
    key: str
    value: str
    provenance: str
    secret: bool
    configured: bool
    externally_managed: bool

    @property
    def display_value(self) -> str:
        if not self.secret:
            return self.value
        return "••••••••" if self.configured else ""


DEFINITIONS = {
    definition.key: definition
    for definition in (
        SettingDefinition("incoming_folder", "general"),
        SettingDefinition("SNAPIMS_RECOGNITION_PROVIDER", "recognition", "openai", choices=("openai", "mock")),
        SettingDefinition("OPENAI_API_KEY", "recognition", secret=True),
        SettingDefinition("SNAPIMS_OPENAI_BASELINE_MODEL", "recognition", "gpt-4.1-mini"),
        SettingDefinition("SNAPIMS_OPENAI_ESCALATION_MODEL", "recognition", "gpt-4.1"),
        SettingDefinition("SNAPIMS_OPENAI_FRONTIER_MODEL", "recognition"),
        SettingDefinition("SNAPIMS_RECOGNITION_CONFIDENCE", "recognition", "0.85"),
        SettingDefinition("SNAPIMS_RECOGNITION_CONTRADICTION_RULES", "recognition", "strict"),
        SettingDefinition("SNAPIMS_RECOGNITION_MAX_ATTEMPTS", "recognition", "3"),
        SettingDefinition("SNAPIMS_RECOGNITION_TIMEOUT_SECONDS", "recognition", "60"),
        SettingDefinition("SNAPIMS_RECOGNITION_RETRY_LIMIT", "recognition", "2"),
        SettingDefinition("SNAPIMS_RECOGNITION_IMAGE_COUNT", "recognition", "3"),
        SettingDefinition("SNAPIMS_RECOGNITION_IMAGE_PROFILE", "recognition", "recognition"),
        SettingDefinition("SNAPIMS_RECOGNITION_PROMPT_VERSION", "recognition", "v1"),
        SettingDefinition("SNAPIMS_CAD_TOKEN_PRICE_TABLE", "recognition", "{}"),
        SettingDefinition("SNAPIMS_CAD_TOKEN_PRICE_VERSION", "recognition", "operator-configured"),
        SettingDefinition("SHOPIFY_STORE_DOMAIN", "shopify"),
        SettingDefinition("SHOPIFY_ADMIN_ACCESS_TOKEN", "shopify", secret=True),
        SettingDefinition("SHOPIFY_LOCATION_ID", "shopify"),
        SettingDefinition("SHOPIFY_API_VERSION", "shopify", "2026-07"),
        SettingDefinition("SHOPIFY_DRAFT_ONLY", "shopify", "true", choices=("true",)),
        SettingDefinition("SNAPIMS_MOVIE_PROVIDER", "movie", "wikipedia", choices=("wikipedia",)),
        SettingDefinition("SNAPIMS_MOVIE_PROVIDER_API_KEY", "movie", secret=True),
        SettingDefinition("SNAPIMS_MOVIE_FIELD_PROFILE", "movie", "core-v1"),
        SettingDefinition("SNAPIMS_MOVIE_LANGUAGE", "movie", "en"),
        SettingDefinition("SNAPIMS_MOVIE_REGION", "movie", "CA"),
        SettingDefinition("SNAPIMS_MOVIE_CACHE_SECONDS", "movie", "86400"),
        SettingDefinition("SNAPIMS_MOVIE_REFRESH_DAYS", "movie", "30"),
        SettingDefinition("SNAPIMS_WIKIPEDIA_USER_AGENT", "movie"),
        SettingDefinition("SNAPIMS_MOVIE_REQUEST_CONCURRENCY", "movie", "1"),
        SettingDefinition("SNAPIMS_WIKIPEDIA_MIN_INTERVAL_SECONDS", "movie", "1.0"),
        SettingDefinition("SNAPIMS_WIKIPEDIA_TIMEOUT_SECONDS", "movie", "10"),
        SettingDefinition("SNAPIMS_WIKIPEDIA_MAX_RETRIES", "movie", "2"),
        SettingDefinition("SNAPIMS_MOVIE_DUMP_LOCATION", "movie"),
        SettingDefinition("SNAPIMS_MOVIE_DUMP_POLICY", "movie", "manual"),
        SettingDefinition("SNAPIMS_ADMIN_USERNAME", "security", "admin"),
        SettingDefinition("SNAPIMS_ADMIN_PASSWORD_HASH", "security", secret=True),
        SettingDefinition("SNAPIMS_AUTH_SECRET", "security", secret=True),
        SettingDefinition("SNAPIMS_SESSION_GENERATION", "security", "1"),
        SettingDefinition("SNAPIMS_BACKUP_RETENTION_DAYS", "backup", "90"),
        SettingDefinition("SNAPIMS_LOG_RETENTION_DAYS", "backup", "30"),
        SettingDefinition("SNAPIMS_EVENT_RETENTION_DAYS", "backup", "365"),
    )
}

SECRET_KEYS = frozenset(key for key, definition in DEFINITIONS.items() if definition.secret)
PERSISTED_PREFIX = "configuration."
SECRET_FILENAME = "provider-secrets.json"


def legacy_environment(
    project_path: Path,
    *,
    process_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ if process_environment is None else process_environment
    if environment.get("SNAPIMS_SKIP_DOTENV"):
        return {}
    path = project_path / ".env"
    if not path.is_file():
        return {}
    return {
        str(key): str(value or "")
        for key, value in dotenv_values(path).items()
        if key
    }


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _filename_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


def _safe_json_object(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if key in SECRET_KEYS and isinstance(value, str)
    }


class ConfigurationService:
    def __init__(
        self,
        *,
        project_path: Path,
        paths: Any,
        process_environment: Mapping[str, str] | None = None,
        legacy: Mapping[str, str] | None = None,
    ) -> None:
        self.project_path = project_path.expanduser().resolve()
        self.paths = paths
        self.process_environment = dict(
            os.environ if process_environment is None else process_environment
        )
        self.legacy = dict(
            legacy
            if legacy is not None
            else legacy_environment(
                self.project_path,
                process_environment=self.process_environment,
            )
        )

    @classmethod
    def load_runtime(cls) -> ConfigurationService:
        from snapims.config import DataPaths, default_project_path

        environment = os.environ
        project = Path(
            environment.get("SNAPIMS_PROJECT_PATH") or default_project_path()
        ).expanduser().resolve()
        legacy = legacy_environment(project, process_environment=environment)
        data_value = (
            environment.get("SNAPIMS_DATA_DIR")
            if "SNAPIMS_DATA_DIR" in environment
            else legacy.get("SNAPIMS_DATA_DIR", "")
        )
        paths = DataPaths.from_root(data_value or None).ensure()
        return cls(
            project_path=project,
            paths=paths,
            process_environment=environment,
            legacy=legacy,
        )

    @property
    def secret_file(self) -> Path:
        return cast(Path, self.paths.secrets / SECRET_FILENAME)

    @property
    def secret_backup_dir(self) -> Path:
        return cast(Path, self.paths.secrets / "backups")

    def _persisted(self, key: str) -> str | None:
        db_file = self.paths.db_file
        if not db_file.is_file():
            return None
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
            ).fetchone()
            if not exists:
                return None
            row = connection.execute(
                "SELECT value FROM settings WHERE key=?",
                (PERSISTED_PREFIX + key,),
            ).fetchone()
            return str(row[0]) if row is not None else None
        except sqlite3.Error:
            return None
        finally:
            if connection is not None:
                connection.close()

    def effective(self, key: str, default: str | None = None) -> EffectiveSetting:
        definition = DEFINITIONS.get(key)
        fallback = definition.default if default is None and definition else (default or "")
        secret = bool(definition and definition.secret)
        if key in self.process_environment:
            value = str(self.process_environment[key])
            return EffectiveSetting(key, value, "environment", secret, bool(value), True)
        if secret:
            stored = self._stored_secrets()
            if key in stored:
                return EffectiveSetting(key, stored[key], "secret store", True, bool(stored[key]), False)
        persisted = self._persisted(key)
        if persisted is not None:
            return EffectiveSetting(key, persisted, "SnapIMS settings", secret, bool(persisted), False)
        if key in self.legacy:
            value = str(self.legacy[key])
            return EffectiveSetting(key, value, "legacy .env", secret, bool(value), False)
        return EffectiveSetting(key, fallback, "default", secret, bool(fallback), False)

    def _stored_secrets(self) -> dict[str, str]:
        if not self.secret_file.exists():
            return {}
        if self.secret_file.is_symlink() or not self.secret_file.is_file():
            raise ConfigurationError("SnapIMS secret store is not a regular file.")
        file_status = self.secret_file.stat()
        directory_status = self.paths.secrets.stat()
        if file_status.st_uid != os.geteuid() or directory_status.st_uid != os.geteuid():
            raise ConfigurationError("SnapIMS secret store must be owned by the service user.")
        if stat.S_IMODE(file_status.st_mode) != 0o600:
            raise ConfigurationError("SnapIMS secret store file permissions must be 0600.")
        if stat.S_IMODE(directory_status.st_mode) != 0o700:
            raise ConfigurationError("SnapIMS secret store directory permissions must be 0700.")
        return _safe_json_object(self.secret_file)

    def value(self, key: str, default: str = "") -> str:
        return self.effective(key, default).value

    def read_model(self, section: str | None = None) -> dict[str, EffectiveSetting]:
        return {
            key: self.effective(key)
            for key, definition in DEFINITIONS.items()
            if section is None or definition.section == section
        }

    def legacy_secret_fields(self) -> tuple[str, ...]:
        return tuple(
            sorted(key for key in SECRET_KEYS if self.legacy.get(key))
        )

    def _ensure_secret_permissions(self) -> None:
        self.paths.secrets.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.paths.secrets.chmod(0o700)
        self.secret_backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.secret_backup_dir.chmod(0o700)
        if self.secret_file.exists():
            self.secret_file.chmod(0o600)

    def _atomic_secret_write(self, payload: Mapping[str, str]) -> str:
        self._ensure_secret_permissions()
        backup_name = f"{_filename_timestamp()}-{SECRET_FILENAME}"
        backup = self.secret_backup_dir / backup_name
        if self.secret_file.is_file():
            backup.write_bytes(self.secret_file.read_bytes())
        else:
            backup.write_text("{}", encoding="utf-8")
        backup.chmod(0o600)
        with backup.open("rb") as handle:
            os.fsync(handle.fileno())
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".provider-secrets-",
            suffix=".tmp",
            dir=self.paths.secrets,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            encoded = json.dumps(
                dict(sorted(payload.items())),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.secret_file)
            self.secret_file.chmod(0o600)
            directory_fd = os.open(self.paths.secrets, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()
        return backup_name

    def _validate(self, key: str, value: str) -> str:
        if key not in DEFINITIONS:
            raise ConfigurationError(f"Unknown configuration field: {key}")
        cleaned = value.strip()
        definition = DEFINITIONS[key]
        if definition.choices and cleaned not in definition.choices:
            raise ConfigurationError(f"{key} must be one of: {', '.join(definition.choices)}")
        if key == "SHOPIFY_STORE_DOMAIN" and cleaned and not re.fullmatch(
            r"[a-z0-9][a-z0-9-]*\.myshopify\.com", cleaned.casefold()
        ):
            raise ConfigurationError("Shopify store domain must end in .myshopify.com.")
        if key == "SHOPIFY_LOCATION_ID" and cleaned and not cleaned.startswith(
            "gid://shopify/Location/"
        ):
            raise ConfigurationError("Shopify location must be a Location GID.")
        if key == "SHOPIFY_API_VERSION" and not re.fullmatch(r"\d{4}-\d{2}", cleaned):
            raise ConfigurationError("Shopify API version must use YYYY-MM.")
        if key == "SNAPIMS_RECOGNITION_CONFIDENCE":
            number = float(cleaned)
            if not 0 <= number <= 1:
                raise ConfigurationError("Recognition confidence must be between 0 and 1.")
        integer_bounds = {
            "SNAPIMS_RECOGNITION_MAX_ATTEMPTS": (1, 10),
            "SNAPIMS_RECOGNITION_TIMEOUT_SECONDS": (1, 300),
            "SNAPIMS_RECOGNITION_RETRY_LIMIT": (0, 10),
            "SNAPIMS_RECOGNITION_IMAGE_COUNT": (1, 10),
            "SNAPIMS_MOVIE_REQUEST_CONCURRENCY": (1, 4),
            "SNAPIMS_WIKIPEDIA_TIMEOUT_SECONDS": (1, 120),
            "SNAPIMS_WIKIPEDIA_MAX_RETRIES": (0, 10),
            "SNAPIMS_BACKUP_RETENTION_DAYS": (1, 3650),
            "SNAPIMS_LOG_RETENTION_DAYS": (1, 3650),
            "SNAPIMS_EVENT_RETENTION_DAYS": (1, 3650),
        }
        if key in integer_bounds:
            minimum, maximum = integer_bounds[key]
            number = int(cleaned)
            if not minimum <= number <= maximum:
                raise ConfigurationError(f"{key} must be between {minimum} and {maximum}.")
        if key == "SNAPIMS_WIKIPEDIA_MIN_INTERVAL_SECONDS":
            if not 0.1 <= float(cleaned) <= 60:
                raise ConfigurationError("Wikipedia request interval must be between 0.1 and 60 seconds.")
        if key == "SNAPIMS_WIKIPEDIA_USER_AGENT" and cleaned:
            if len(cleaned) < 12 or not any(marker in cleaned for marker in ("@", "http://", "https://")):
                raise ConfigurationError("Wikimedia User-Agent must identify SnapIMS and include contact information.")
        if key == "SNAPIMS_CAD_TOKEN_PRICE_TABLE":
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ConfigurationError("CAD token price table must be a JSON object.")
        return cleaned

    def _record_revision(
        self,
        *,
        section: str,
        changed_fields: list[str],
        previous: Mapping[str, Any] | None = None,
        replacement: Mapping[str, Any] | None = None,
        secret: bool = False,
        backup_reference: str = "",
        status: str = "APPLIED",
    ) -> str:
        from snapims import db

        db.initialize(self.paths.db_file, paths=self.paths)
        revision_id = uuid4().hex
        with db.transaction(self.paths.db_file) as connection:
            connection.execute(
                """INSERT INTO configuration_revisions(
                       revision_id,created_at,section,changed_fields_json,
                       previous_values_json,new_values_json,contains_secrets,
                       backup_reference,status
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    revision_id,
                    _timestamp(),
                    section,
                    json.dumps(sorted(changed_fields)),
                    "{}" if secret else json.dumps(dict(previous or {}), sort_keys=True),
                    "{}" if secret else json.dumps(dict(replacement or {}), sort_keys=True),
                    int(secret),
                    backup_reference,
                    status,
                ),
            )
        return revision_id

    def save_nonsecret(self, section: str, changes: Mapping[str, str]) -> str:
        from snapims import db

        if not changes:
            raise ConfigurationError("No settings were supplied.")
        cleaned: dict[str, str] = {}
        previous: dict[str, Any] = {}
        for key, raw in changes.items():
            definition = DEFINITIONS.get(key)
            if definition is None or definition.secret or definition.section != section:
                raise ConfigurationError(f"{key} cannot be saved in {section}.")
            if key in self.process_environment:
                raise ConfigurationError(f"{key} is managed by the process environment.")
            cleaned[key] = self._validate(key, raw)
            previous[key] = self._persisted(key)
        model_fields = {
            "SNAPIMS_OPENAI_BASELINE_MODEL",
            "SNAPIMS_OPENAI_ESCALATION_MODEL",
            "SNAPIMS_OPENAI_FRONTIER_MODEL",
        }
        selected_models = {
            value for key, value in cleaned.items() if key in model_fields and value
        }
        untested = selected_models - set(self.compatible_models())
        if untested:
            raise ConfigurationError(
                "Recognition role models must pass the image and strict-schema probe first: "
                + ", ".join(sorted(untested))
            )
        db.initialize(self.paths.db_file, paths=self.paths)
        backup = db.backup_database(self.paths, f"before-{section}-settings")
        with db.transaction(self.paths.db_file) as connection:
            for key, value in cleaned.items():
                connection.execute(
                    """INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)
                       ON CONFLICT(key) DO UPDATE SET
                           value=excluded.value,updated_at=excluded.updated_at""",
                    (PERSISTED_PREFIX + key, value, _timestamp()),
                )
        for key, value in cleaned.items():
            effective = self.effective(key)
            if effective.value != value:
                raise ConfigurationError(
                    f"{key} did not become effective; it is supplied by {effective.provenance}."
                )
        return self._record_revision(
            section=section,
            changed_fields=list(cleaned),
            previous=previous,
            replacement=cleaned,
            backup_reference=backup.name if backup else "",
        )

    def rollback_nonsecret(self, revision_id: str) -> str:
        from snapims import db

        db.initialize(self.paths.db_file, paths=self.paths)
        with db.connect(self.paths.db_file) as connection:
            row = connection.execute(
                """SELECT section,changed_fields_json,previous_values_json,contains_secrets
                   FROM configuration_revisions WHERE revision_id=?""",
                (revision_id,),
            ).fetchone()
        if row is None or bool(row["contains_secrets"]):
            raise ConfigurationError("A non-secret configuration revision was not found.")
        section = str(row["section"])
        fields = json.loads(str(row["changed_fields_json"]))
        previous = json.loads(str(row["previous_values_json"]))
        if not isinstance(fields, list) or not isinstance(previous, dict):
            raise ConfigurationError("Configuration revision is malformed.")
        backup = db.backup_database(self.paths, f"before-{section}-rollback")
        replacement: dict[str, str] = {}
        current_values = {
            str(field): self._persisted(str(field))
            for field in fields
            if isinstance(field, str)
        }
        with db.transaction(self.paths.db_file) as connection:
            for field in fields:
                if not isinstance(field, str) or field not in DEFINITIONS:
                    raise ConfigurationError("Configuration revision contains an invalid field.")
                old_value = previous.get(field)
                if old_value is None:
                    connection.execute(
                        "DELETE FROM settings WHERE key=?",
                        (PERSISTED_PREFIX + field,),
                    )
                    replacement[field] = ""
                else:
                    restored = str(old_value)
                    connection.execute(
                        """INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)
                           ON CONFLICT(key) DO UPDATE SET
                               value=excluded.value,updated_at=excluded.updated_at""",
                        (PERSISTED_PREFIX + field, restored, _timestamp()),
                    )
                    replacement[field] = restored
        return self._record_revision(
            section=section,
            changed_fields=[str(field) for field in fields],
            previous=current_values,
            replacement=replacement,
            backup_reference=backup.name if backup else "",
            status="ROLLED_BACK",
        )

    def save_secrets(self, section: str, changes: Mapping[str, str]) -> str:
        if not changes:
            raise ConfigurationError("No secrets were supplied.")
        stored = self._stored_secrets()
        changed_fields: list[str] = []
        for key, raw in changes.items():
            definition = DEFINITIONS.get(key)
            if definition is None or not definition.secret or definition.section != section:
                raise ConfigurationError(f"{key} is not a {section} secret.")
            if key in self.process_environment:
                raise ConfigurationError(f"{key} is managed by the process environment.")
            value = self._validate(key, raw)
            if not value:
                raise ConfigurationError(f"{key} cannot be empty.")
            stored[key] = value
            changed_fields.append(key)
        backup = self._atomic_secret_write(stored)
        for key in changed_fields:
            if self.effective(key).value != stored[key]:
                raise ConfigurationError(f"{key} failed post-write verification.")
        return self._record_revision(
            section=section,
            changed_fields=changed_fields,
            secret=True,
            backup_reference=backup,
        )

    def migrate_legacy_secrets(self, fields: list[str]) -> str:
        changes: dict[str, str] = {}
        sections = {
            DEFINITIONS[field].section
            for field in fields
            if field in SECRET_KEYS and self.legacy.get(field)
        }
        if len(sections) != 1:
            raise ConfigurationError("Migrate one secret section at a time.")
        for field in fields:
            if field not in SECRET_KEYS or not self.legacy.get(field):
                raise ConfigurationError(f"{field} is not an available legacy secret.")
            changes[field] = self.legacy[field]
        return self.save_secrets(sections.pop(), changes)

    def rollback_secret_file(self, backup_name: str, *, section: str) -> str:
        if Path(backup_name).name != backup_name:
            raise ConfigurationError("Invalid secret backup reference.")
        backup = self.secret_backup_dir / backup_name
        if not backup.is_file():
            raise ConfigurationError("Secret backup was not found.")
        payload = _safe_json_object(backup)
        current = _safe_json_object(self.secret_file)
        new_backup = self._atomic_secret_write(payload)
        changed_fields = sorted(set(current) | set(payload))
        return self._record_revision(
            section=section,
            changed_fields=changed_fields,
            secret=True,
            backup_reference=new_backup,
            status="ROLLED_BACK",
        )

    def revisions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        from snapims import db

        db.initialize(self.paths.db_file, paths=self.paths)
        with db.connect(self.paths.db_file) as connection:
            rows = connection.execute(
                """SELECT revision_id,created_at,section,changed_fields_json,
                          contains_secrets,backup_reference,status
                   FROM configuration_revisions
                   ORDER BY created_at DESC LIMIT ?""",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [
            {
                "revision_id": str(row["revision_id"]),
                "created_at": str(row["created_at"]),
                "section": str(row["section"]),
                "changed_fields": json.loads(str(row["changed_fields_json"])),
                "contains_secrets": bool(row["contains_secrets"]),
                "backup_reference": str(row["backup_reference"]),
                "status": str(row["status"]),
            }
            for row in rows
        ]

    def save_model_capability(
        self,
        *,
        model_id: str,
        supports_images: bool,
        supports_strict_schema: bool,
        status: str,
        safe_summary: str = "",
        probe_version: str = "responses-v1",
    ) -> None:
        from snapims import db

        db.initialize(self.paths.db_file, paths=self.paths)
        with db.transaction(self.paths.db_file) as connection:
            connection.execute(
                """INSERT INTO provider_model_capabilities(
                       provider,model_id,discovered_at,supports_images,
                       supports_strict_schema,test_status,probe_version,safe_summary
                   ) VALUES('openai',?,?,?,?,?,?,?)
                   ON CONFLICT(provider,model_id) DO UPDATE SET
                       discovered_at=excluded.discovered_at,
                       supports_images=excluded.supports_images,
                       supports_strict_schema=excluded.supports_strict_schema,
                       test_status=excluded.test_status,
                       probe_version=excluded.probe_version,
                       safe_summary=excluded.safe_summary""",
                (
                    model_id,
                    _timestamp(),
                    int(supports_images),
                    int(supports_strict_schema),
                    status,
                    probe_version,
                    safe_summary[:500],
                ),
            )

    def compatible_models(self) -> list[str]:
        from snapims import db

        db.initialize(self.paths.db_file, paths=self.paths)
        with db.connect(self.paths.db_file) as connection:
            rows = connection.execute(
                """SELECT model_id FROM provider_model_capabilities
                   WHERE provider='openai' AND supports_images=1
                     AND supports_strict_schema=1 AND test_status='PASS'
                   ORDER BY model_id"""
            ).fetchall()
        return [str(row[0]) for row in rows]
