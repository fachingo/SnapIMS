from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image, ImageOps

from snapims import db
from snapims.config import DataPaths
from snapims.interpreter import make_batch_id
from snapims.models import BatchRecord, ItemRecord, PhotoRecord
from snapims.processor import process_batch
from snapims.protocol import CommandKind, parse_command
from snapims.sorter import SUPPORTED_EXTENSIONS

NEXT_PAYLOAD = "CVHS1:ITEM:NEXT"
LEGACY_FIXED = {
    "CVHS1:BATCH:START",
    "CVHS1:BATCH:END",
    "CVHS1:ITEM:CONT",
    "CVHS1:FLAG:RARE",
    "CVHS1:FLAG:REVIEW",
}
_FILENAME_TIME = re.compile(r"(20\d{6})[_-]?(\d{6})(\d{0,6})")
_THREAD_LOCAL = threading.local()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="snapims-import")
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_JOBS: set[str] = set()
_ACTIVE_JOB_STATUSES = (
    "QUEUED",
    "RUNNING",
    "READY",
    "NEEDS_ATTENTION",
    "COMMIT_QUEUED",
    "COMMITTING",
)


@dataclass(frozen=True, slots=True)
class FileIdentity:
    path: str
    name: str
    size: int
    mtime_ns: int
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class ScanResult:
    source_path: str
    folder_path: str
    original_name: str
    file_size: int
    mtime_ns: int
    device: int
    inode: int
    captured_at: str
    timestamp_source: str
    width: int
    height: int
    qr_payload: str | None
    classification: str
    read_error: str
    thumbnail_path: str
    decode_count: int
    qr_scan_count: int
    full_resolution_fallbacks: int
    filesystem_reads: int


class ImportV0130Error(RuntimeError):
    pass


def normalize_location(value: object) -> str | None:
    location = str(value or "").strip()
    if not location or location.casefold() == "none":
        return None
    if any(ord(character) < 32 for character in location):
        raise ImportV0130Error("Batch location contains unsupported control characters.")
    if len(location) > 120:
        raise ImportV0130Error("Batch location must be 120 characters or fewer.")
    return location


def location_warning(location: str | None) -> str:
    if not location:
        return ""
    if re.fullmatch(r"(?i)(Q1|[A-J](?:[1-9]|10))", location):
        return ""
    return "This location is free text and does not match the former shelf-card format. It will still be accepted."


def batch_home(paths: DataPaths) -> Path:
    configured = os.getenv("SNAPIMS_BATCH_HOME", "").strip()
    return Path(configured).expanduser().resolve() if configured else paths.batches.resolve()


def ensure_batch_home(paths: DataPaths) -> Path:
    home = batch_home(paths)
    home.mkdir(parents=True, exist_ok=True)
    return home


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _safe_folder(folder: Path, paths: DataPaths) -> Path:
    home = ensure_batch_home(paths)
    resolved = folder.expanduser().resolve()
    if resolved.parent != home:
        raise ImportV0130Error(
            f"Select one immediate child folder inside the Batch Home Directory: {home}"
        )
    if not resolved.is_dir():
        raise ImportV0130Error("Selected batch folder is not available.")
    return resolved


def _metadata_fingerprint(rows: list[dict[str, Any]], corrections: dict[str, dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        path = str(row["source_path"])
        digest.update(path.encode("utf-8", errors="surrogatepass"))
        digest.update(b"\0")
        digest.update(str(int(row["file_size"])).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(int(row["mtime_ns"])).encode("ascii"))
        digest.update(b"\0")
        correction = corrections.get(path) or {}
        digest.update(json.dumps(correction, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _cache_id(source_path: str) -> str:
    return hashlib.sha256(source_path.encode("utf-8", errors="surrogatepass")).hexdigest()[:32]


def _folder_cache_root(paths: DataPaths, folder: Path) -> Path:
    key = hashlib.sha256(str(folder).encode("utf-8", errors="surrogatepass")).hexdigest()[:24]
    root = paths.import_cache / key
    root.mkdir(parents=True, exist_ok=True)
    return root


def _inventory(folder: Path) -> list[FileIdentity]:
    files: list[FileIdentity] = []
    with os.scandir(folder) as entries:
        for entry in entries:
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if Path(entry.name).suffix.casefold() not in SUPPORTED_EXTENSIONS:
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            files.append(
                FileIdentity(
                    path=str(Path(entry.path).resolve()),
                    name=entry.name,
                    size=int(stat.st_size),
                    mtime_ns=int(stat.st_mtime_ns),
                    device=int(stat.st_dev),
                    inode=int(stat.st_ino),
                )
            )
    files.sort(key=lambda row: (row.name.casefold(), row.path.casefold()))
    return files


def _capture_time(opened: Image.Image, identity: FileIdentity) -> tuple[datetime, str]:
    try:
        exif = opened.getexif()
        for tag in (36867, 36868, 306):
            raw = exif.get(tag)
            if raw:
                return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S"), "exif"
    except (OSError, ValueError, TypeError):
        pass
    match = _FILENAME_TIME.search(Path(identity.name).stem)
    if match:
        base = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
        micro = (match.group(3) + "000000")[:6]
        return base.replace(microsecond=int(micro)), "filename"
    return datetime.fromtimestamp(identity.mtime_ns / 1_000_000_000), "filesystem_mtime"


def _detector() -> cv2.QRCodeDetector:
    detector = getattr(_THREAD_LOCAL, "qr_detector", None)
    if detector is None:
        detector = cv2.QRCodeDetector()
        _THREAD_LOCAL.qr_detector = detector
    return detector


def _classify_payload(payload: str | None) -> str:
    normalized = str(payload or "").strip().upper()
    if normalized == NEXT_PAYLOAD:
        return "next"
    if normalized in LEGACY_FIXED or normalized.startswith("CVHS1:LOC:"):
        return "legacy"
    command = parse_command(normalized) if normalized else None
    if command is not None and command.kind != CommandKind.ITEM_NEXT:
        return "legacy"
    return "product"


def _decode_qr(scan_image: Image.Image) -> tuple[str | None, bool]:
    detector = _detector()
    grayscale = np.asarray(scan_image.convert("L"))
    try:
        payload, points, _ = detector.detectAndDecode(grayscale)
    except cv2.error:
        payload, points = "", None
    return (payload.strip() or None), points is not None


def _scan_one(identity: FileIdentity, folder: Path, paths: DataPaths) -> ScanResult:
    thumbnail = _folder_cache_root(paths, folder) / f"{_cache_id(identity.path)}.jpg"
    decode_count = 0
    qr_scan_count = 0
    fallback_count = 0
    reads = 1
    try:
        with Image.open(identity.path) as opened:
            captured, timestamp_source = _capture_time(opened, identity)
            width, height = opened.size
            # JPEG draft mode asks the decoder for a reduced native-resolution image.
            # This avoids decoding a full Pixel photograph merely to find a QR card.
            try:
                opened.draft("RGB", (480, 480))
            except (OSError, ValueError):
                pass
            scan_image = ImageOps.exif_transpose(opened).convert("RGB")
            scan_image.thumbnail((480, 480), Image.Resampling.BILINEAR)
            decode_count = 1
            qr_scan_count = 1
            payload, candidate = _decode_qr(scan_image)
            if not payload and candidate:
                fallback_count = 1
                reads += 1
                with Image.open(identity.path) as full_opened:
                    full_image = ImageOps.exif_transpose(full_opened).convert("RGB")
                    payload, _ = _decode_qr(full_image)
            if not thumbnail.is_file():
                preview = scan_image.copy()
                preview.thumbnail((360, 360), Image.Resampling.LANCZOS)
                thumbnail.parent.mkdir(parents=True, exist_ok=True)
                temporary = thumbnail.with_suffix(".tmp.jpg")
                preview.save(temporary, format="JPEG", quality=76, optimize=False)
                os.replace(temporary, thumbnail)
        classification = _classify_payload(payload)
        read_error = ""
    except (OSError, ValueError, cv2.error) as exc:
        captured = datetime.fromtimestamp(identity.mtime_ns / 1_000_000_000)
        timestamp_source = "filesystem_mtime"
        width = 0
        height = 0
        payload = None
        classification = "error"
        read_error = f"{type(exc).__name__}: {exc}"
    return ScanResult(
        source_path=identity.path,
        folder_path=str(folder),
        original_name=identity.name,
        file_size=identity.size,
        mtime_ns=identity.mtime_ns,
        device=identity.device,
        inode=identity.inode,
        captured_at=captured.isoformat(timespec="microseconds"),
        timestamp_source=timestamp_source,
        width=width,
        height=height,
        qr_payload=payload,
        classification=classification,
        read_error=read_error,
        thumbnail_path=str(thumbnail) if thumbnail.is_file() else "",
        decode_count=decode_count,
        qr_scan_count=qr_scan_count,
        full_resolution_fallbacks=fallback_count,
        filesystem_reads=reads,
    )


def _cache_parameters(result: ScanResult) -> tuple[Any, ...]:
    return (
        result.source_path,
        _cache_id(result.source_path),
        result.folder_path,
        result.original_name,
        result.file_size,
        result.mtime_ns,
        result.device,
        result.inode,
        result.captured_at,
        result.timestamp_source,
        result.width,
        result.height,
        result.qr_payload,
        result.classification,
        result.read_error,
        result.thumbnail_path,
        "",
        _iso_now(),
        result.decode_count,
        result.qr_scan_count,
        result.full_resolution_fallbacks,
        result.filesystem_reads,
    )


_CACHE_UPSERT_SQL = """INSERT INTO import_photo_cache(
       source_path,cache_id,folder_path,original_name,file_size,mtime_ns,device,inode,
       captured_at,timestamp_source,width,height,qr_payload,classification,
       read_error,thumbnail_path,sha256,scanned_at,decode_count,qr_scan_count,
       full_resolution_fallbacks,filesystem_reads
   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
   ON CONFLICT(source_path) DO UPDATE SET
       cache_id=excluded.cache_id,folder_path=excluded.folder_path,
       original_name=excluded.original_name,file_size=excluded.file_size,
       mtime_ns=excluded.mtime_ns,device=excluded.device,inode=excluded.inode,
       captured_at=excluded.captured_at,timestamp_source=excluded.timestamp_source,
       width=excluded.width,height=excluded.height,qr_payload=excluded.qr_payload,
       classification=excluded.classification,read_error=excluded.read_error,
       thumbnail_path=excluded.thumbnail_path,
       sha256=CASE WHEN import_photo_cache.file_size=excluded.file_size
                      AND import_photo_cache.mtime_ns=excluded.mtime_ns
                      AND import_photo_cache.device=excluded.device
                      AND import_photo_cache.inode=excluded.inode
                   THEN import_photo_cache.sha256 ELSE '' END,
       scanned_at=excluded.scanned_at,decode_count=excluded.decode_count,
       qr_scan_count=excluded.qr_scan_count,
       full_resolution_fallbacks=excluded.full_resolution_fallbacks,
       filesystem_reads=excluded.filesystem_reads"""


def _upsert_cache_many(db_file: Path, results: list[ScanResult]) -> None:
    if not results:
        return
    with db.transaction(db_file) as connection:
        connection.executemany(_CACHE_UPSERT_SQL, [_cache_parameters(result) for result in results])


def _cache_rows(db_file: Path, folder: Path) -> list[dict[str, Any]]:
    with db.connect(db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM import_photo_cache WHERE folder_path=? ORDER BY captured_at,lower(original_name),source_path",
            (str(folder),),
        ).fetchall()
    return [dict(row) for row in rows]


def _corrections(db_file: Path, folder: Path) -> dict[str, dict[str, Any]]:
    with db.connect(db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM import_photo_corrections WHERE folder_path=?",
            (str(folder),),
        ).fetchall()
    return {str(row["source_path"]): dict(row) for row in rows}


def _effective_kind(row: dict[str, Any], correction: dict[str, Any] | None) -> str:
    action = str((correction or {}).get("action") or "auto")
    if action == "product":
        return "product"
    if action == "next":
        return "next"
    if action == "ignore":
        return "ignore"
    classification = str(row.get("classification") or "product")
    if classification in {"legacy", "error"}:
        return "ignore"
    return classification


def build_preview(db_file: Path, folder: Path, *, location: str | None = None) -> dict[str, Any]:
    inventory = _inventory(folder)
    current_paths = {row.path for row in inventory}
    rows = [row for row in _cache_rows(db_file, folder) if str(row["source_path"]) in current_paths]
    rows.sort(
        key=lambda row: (
            str(row.get("captured_at") or ""),
            str(row.get("original_name") or "").casefold(),
            str(row.get("source_path") or "").casefold(),
        )
    )
    corrections = _corrections(db_file, folder)
    warnings: list[str] = []
    legacy_count = sum(1 for row in rows if row.get("classification") == "legacy")
    unreadable = [row for row in rows if row.get("classification") == "error"]
    if legacy_count:
        warnings.append(f"{legacy_count} legacy SnapIMS command photograph(s) were ignored.")
    if unreadable:
        warnings.append(
            f"{len(unreadable)} unreadable photograph(s) were ignored. Replace or explicitly classify them before relying on the batch."
        )
    location_note = location_warning(location)
    if location_note:
        warnings.append(location_note)

    items: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    pending_boundary = False
    leading_next = 0
    consecutive_next = 0
    trailing_next = False
    previous_was_next = False
    command_count = 0
    product_count = 0

    for row in rows:
        source_path = str(row["source_path"])
        correction = corrections.get(source_path)
        kind = _effective_kind(row, correction)
        split_before = bool((correction or {}).get("split_before"))
        merge_previous = bool((correction or {}).get("merge_previous"))
        photo = {
            "cache_id": _cache_id(source_path),
            "source_path": source_path,
            "name": str(row["original_name"]),
            "kind": kind,
            "correction_action": str((correction or {}).get("action") or "auto"),
            "default_kind": str(row.get("classification") or "product"),
            "thumbnail_available": bool(row.get("thumbnail_path")),
            "read_error": str(row.get("read_error") or ""),
            "qr_payload": str(row.get("qr_payload") or ""),
            "split_before": split_before,
            "merge_previous": merge_previous,
        }
        if kind == "ignore":
            continue
        if kind == "next":
            command_count += 1
            if not current and not items:
                leading_next += 1
            elif pending_boundary:
                consecutive_next += 1
            pending_boundary = True
            previous_was_next = True
            continue

        product_count += 1
        if split_before and current:
            items.append(current)
            current = []
            pending_boundary = False
        if pending_boundary:
            if current and not merge_previous:
                items.append(current)
                current = []
            pending_boundary = False
        current.append(photo)
        previous_was_next = False

    if current:
        items.append(current)
    elif pending_boundary and (items or product_count):
        trailing_next = True

    if leading_next:
        warnings.append(f"{leading_next} leading NEXT ITEM photograph(s) were ignored.")
    if consecutive_next:
        warnings.append(f"{consecutive_next} consecutive NEXT ITEM photograph(s) were collapsed.")
    if trailing_next or (previous_was_next and product_count):
        warnings.append("A trailing NEXT ITEM photograph was ignored; no empty Item was created.")
    if not product_count:
        warnings.append("No product photographs exist in this folder.")

    item_payload = [
        {"sequence": index, "photos": photos, "photo_count": len(photos)}
        for index, photos in enumerate(items, start=1)
    ]
    return {
        "folder_path": str(folder),
        "folder_name": folder.name,
        "batch_name": folder.name,
        "location": location,
        "location_display": location or "Unassigned",
        "items": item_payload,
        "item_count": len(item_payload),
        "product_photo_count": product_count,
        "next_count": command_count,
        "legacy_count": legacy_count,
        "unreadable_count": len(unreadable),
        "warning_count": len(warnings),
        "warnings": warnings,
        "can_commit": bool(item_payload and product_count),
        "metadata_fingerprint": _metadata_fingerprint(rows, corrections),
    }


def _update_job(db_file: Path, job_id: str, **values: Any) -> None:
    if not values:
        return
    values["updated_at"] = _iso_now()
    assignments = ",".join(f"{key}=?" for key in values)
    with db.transaction(db_file) as connection:
        connection.execute(
            f"UPDATE import_jobs SET {assignments} WHERE job_id=?",
            (*values.values(), job_id),
        )


def get_job(db_file: Path, job_id: str) -> dict[str, Any] | None:
    with db.connect(db_file) as connection:
        row = connection.execute("SELECT * FROM import_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["preview"] = json.loads(str(result.get("preview_json") or "{}"))
    except json.JSONDecodeError:
        result["preview"] = {}
    try:
        result["warnings"] = json.loads(str(result.get("warnings_json") or "[]"))
    except json.JSONDecodeError:
        result["warnings"] = []
    started = str(result.get("started_at") or "")
    if started:
        try:
            result["elapsed_seconds"] = max(
                0.0,
                (datetime.now().astimezone() - datetime.fromisoformat(started)).total_seconds(),
            )
        except ValueError:
            result["elapsed_seconds"] = 0.0
    else:
        result["elapsed_seconds"] = 0.0
    return result


def _job_is_active(job_id: str) -> bool:
    with _ACTIVE_LOCK:
        return job_id in _ACTIVE_JOBS


def _mark_active(job_id: str, active: bool) -> None:
    with _ACTIVE_LOCK:
        if active:
            _ACTIVE_JOBS.add(job_id)
        else:
            _ACTIVE_JOBS.discard(job_id)


def _active_job_for_folder(
    connection: sqlite3.Connection, folder_path: str
) -> sqlite3.Row | None:
    placeholders = ",".join("?" for _ in _ACTIVE_JOB_STATUSES)
    return connection.execute(
        f"""SELECT * FROM import_jobs
                WHERE folder_path=? AND status IN ({placeholders})
                ORDER BY created_at DESC,job_id DESC LIMIT 1""",
        (folder_path, *_ACTIVE_JOB_STATUSES),
    ).fetchone()


def start_preview(paths: DataPaths, folder: Path, *, location: object = None) -> str:
    db.initialize(paths.db_file, paths=paths)
    selected = _safe_folder(folder, paths)
    selected_path = str(selected)
    normalized_location = normalize_location(location)
    timestamp = _iso_now()
    proposed_job_id = uuid4().hex
    created = False
    with db.transaction(paths.db_file) as connection:
        existing = _active_job_for_folder(connection, selected_path)
        if existing is not None:
            job_id = str(existing["job_id"])
            existing_status = str(existing["status"])
            if existing_status in {"READY", "NEEDS_ATTENTION"}:
                connection.execute(
                    """UPDATE import_jobs
                          SET batch_location=?,status='QUEUED',stage='Queued',
                              processed_count=0,total_count=0,error_message='',
                              completed_at=NULL,decode_count=0,qr_scan_count=0,
                              full_hash_count=0,filesystem_reads=0,cache_hits=0,
                              cache_misses=0,updated_at=?
                        WHERE job_id=?""",
                    (normalized_location, timestamp, job_id),
                )
        else:
            try:
                connection.execute(
                    """INSERT INTO import_jobs(
                           job_id,folder_path,folder_name,batch_name,batch_location,status,stage,
                           processed_count,total_count,preview_json,warnings_json,error_message,
                           created_at,started_at,updated_at,completed_at,decode_count,qr_scan_count,
                           full_hash_count,filesystem_reads,cache_hits,cache_misses,result_batch_id
                       ) VALUES(?,?,?,?,?,'QUEUED','Queued',0,0,'{}','[]','',?,?,?,NULL,0,0,0,0,0,0,'')""",
                    (
                        proposed_job_id,
                        selected_path,
                        selected.name,
                        selected.name,
                        normalized_location,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                job_id = proposed_job_id
                created = True
            except sqlite3.IntegrityError:
                existing = _active_job_for_folder(connection, selected_path)
                if existing is None:
                    raise
                job_id = str(existing["job_id"])
    existing_job = get_job(paths.db_file, job_id)
    if created or (existing_job and str(existing_job.get("status")) in {"QUEUED", "RUNNING"}):
        _submit_preview(paths, job_id)
    return job_id


def _submit_preview(paths: DataPaths, job_id: str) -> None:
    if _job_is_active(job_id):
        return
    _mark_active(job_id, True)
    _EXECUTOR.submit(_run_preview, paths, job_id)


def _run_preview(paths: DataPaths, job_id: str) -> None:
    started = time.perf_counter()
    try:
        job = get_job(paths.db_file, job_id)
        if not job:
            return
        folder = _safe_folder(Path(str(job["folder_path"])), paths)
        _update_job(
            paths.db_file,
            job_id,
            status="RUNNING",
            stage="Inventorying folder",
            started_at=_iso_now(),
            error_message="",
        )
        inventory = _inventory(folder)
        _update_job(paths.db_file, job_id, total_count=len(inventory), stage="Checking cache")
        with db.connect(paths.db_file) as connection:
            cached_rows = connection.execute(
                "SELECT source_path,file_size,mtime_ns,device,inode FROM import_photo_cache WHERE folder_path=?",
                (str(folder),),
            ).fetchall()
        cached = {str(row["source_path"]): dict(row) for row in cached_rows}
        missing: list[FileIdentity] = []
        hits = 0
        for identity in inventory:
            row = cached.get(identity.path)
            if (
                row
                and int(row["file_size"]) == identity.size
                and int(row["mtime_ns"]) == identity.mtime_ns
                and int(row["device"]) == identity.device
                and int(row["inode"]) == identity.inode
            ):
                hits += 1
            else:
                missing.append(identity)
        _update_job(
            paths.db_file,
            job_id,
            cache_hits=hits,
            cache_misses=len(missing),
            processed_count=hits,
            stage="Using cached analysis" if not missing else "Scanning changed photographs",
        )
        decode_count = 0
        qr_count = 0
        fallback_count = 0
        fs_reads = 1
        if missing:
            configured_workers = int(os.getenv("SNAPIMS_IMPORT_WORKERS", "2") or 2)
            if os.getenv("SNAPIMS_LOW_MEMORY", "").strip().casefold() in {"1", "true", "yes", "on"}:
                configured_workers = 1
            worker_count = max(1, min(2, configured_workers))
            pending_writes: list[ScanResult] = []
            last_progress_write = 0.0
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="snapims-photo") as pool:
                futures = {pool.submit(_scan_one, identity, folder, paths): identity for identity in missing}
                processed = hits
                for future in as_completed(futures):
                    result = future.result()
                    pending_writes.append(result)
                    decode_count += result.decode_count
                    qr_count += result.qr_scan_count
                    fallback_count += result.full_resolution_fallbacks
                    fs_reads += result.filesystem_reads
                    processed += 1
                    now_monotonic = time.monotonic()
                    should_flush = len(pending_writes) >= 8 or processed == len(inventory)
                    if should_flush:
                        _upsert_cache_many(paths.db_file, pending_writes)
                        pending_writes.clear()
                    if should_flush or now_monotonic - last_progress_write >= 0.20:
                        _update_job(
                            paths.db_file,
                            job_id,
                            processed_count=processed,
                            stage=f"Scanning {processed} of {len(inventory)} photographs",
                            decode_count=decode_count,
                            qr_scan_count=qr_count,
                            filesystem_reads=fs_reads,
                        )
                        last_progress_write = now_monotonic
            _upsert_cache_many(paths.db_file, pending_writes)
        # Remove stale cache rows only from this folder; thumbnails are retained harmlessly.
        current_paths = {identity.path for identity in inventory}
        with db.transaction(paths.db_file) as connection:
            stale = connection.execute(
                "SELECT source_path FROM import_photo_cache WHERE folder_path=?",
                (str(folder),),
            ).fetchall()
            for row in stale:
                if str(row[0]) not in current_paths:
                    connection.execute("DELETE FROM import_photo_cache WHERE source_path=?", (str(row[0]),))
                    connection.execute("DELETE FROM import_photo_corrections WHERE source_path=?", (str(row[0]),))
        preview = build_preview(
            paths.db_file,
            folder,
            location=normalize_location(job.get("batch_location")),
        )
        elapsed = time.perf_counter() - started
        status = "READY" if preview["can_commit"] else "NEEDS_ATTENTION"
        _update_job(
            paths.db_file,
            job_id,
            status=status,
            stage="Preview ready" if status == "READY" else "Preview needs attention",
            processed_count=len(inventory),
            preview_json=json.dumps(preview, sort_keys=True, separators=(",", ":")),
            warnings_json=json.dumps(preview["warnings"], ensure_ascii=False),
            completed_at=_iso_now(),
            decode_count=decode_count,
            qr_scan_count=qr_count,
            filesystem_reads=fs_reads,
            duration_ms=int(elapsed * 1000),
        )
    except Exception as exc:
        _update_job(
            paths.db_file,
            job_id,
            status="FAILED",
            stage="Preview failed",
            error_message=f"{type(exc).__name__}: {exc}",
            completed_at=_iso_now(),
        )
    finally:
        _mark_active(job_id, False)


def refresh_preview_from_cache(paths: DataPaths, job_id: str) -> dict[str, Any]:
    job = get_job(paths.db_file, job_id)
    if not job:
        raise ImportV0130Error("Import job was not found.")
    folder = _safe_folder(Path(str(job["folder_path"])), paths)
    preview = build_preview(paths.db_file, folder, location=normalize_location(job.get("batch_location")))
    status = "READY" if preview["can_commit"] else "NEEDS_ATTENTION"
    _update_job(
        paths.db_file,
        job_id,
        status=status,
        stage="Preview ready" if status == "READY" else "Preview needs attention",
        preview_json=json.dumps(preview, sort_keys=True, separators=(",", ":")),
        warnings_json=json.dumps(preview["warnings"], ensure_ascii=False),
        completed_at=_iso_now(),
    )
    return preview


def apply_correction(
    paths: DataPaths,
    job_id: str,
    source_path: str,
    *,
    action: str = "auto",
    split_before: bool = False,
    merge_previous: bool = False,
) -> dict[str, Any]:
    job = get_job(paths.db_file, job_id)
    if not job:
        raise ImportV0130Error("Import job was not found.")
    folder = _safe_folder(Path(str(job["folder_path"])), paths)
    resolved = Path(source_path).resolve()
    if resolved.parent != folder:
        raise ImportV0130Error("Photo correction does not belong to this batch folder.")
    if action not in {"auto", "product", "next", "ignore"}:
        raise ImportV0130Error("Unsupported photo interpretation.")
    with db.transaction(paths.db_file) as connection:
        if action == "auto" and not split_before and not merge_previous:
            connection.execute(
                "DELETE FROM import_photo_corrections WHERE folder_path=? AND source_path=?",
                (str(folder), str(resolved)),
            )
        else:
            connection.execute(
                """INSERT INTO import_photo_corrections(
                       folder_path,source_path,action,split_before,merge_previous,updated_at
                   ) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(folder_path,source_path) DO UPDATE SET
                       action=excluded.action,split_before=excluded.split_before,
                       merge_previous=excluded.merge_previous,updated_at=excluded.updated_at""",
                (
                    str(folder),
                    str(resolved),
                    action,
                    int(split_before),
                    int(merge_previous),
                    _iso_now(),
                ),
            )
    return refresh_preview_from_cache(paths, job_id)


def _hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _materialize_batch(paths: DataPaths, job: dict[str, Any]) -> tuple[BatchRecord, int]:
    folder = _safe_folder(Path(str(job["folder_path"])), paths)
    preview = build_preview(paths.db_file, folder, location=normalize_location(job.get("batch_location")))
    if not preview["can_commit"]:
        raise ImportV0130Error("Preview contains no committable Items.")
    inventory = _inventory(folder)
    by_path = {row.path: row for row in inventory}
    rows = [row for row in _cache_rows(paths.db_file, folder) if str(row["source_path"]) in by_path]
    # Verify unchanged metadata before any full hash work.
    changed: list[FileIdentity] = []
    for row in rows:
        identity = by_path[str(row["source_path"])]
        if (
            int(row["file_size"]) != identity.size
            or int(row["mtime_ns"]) != identity.mtime_ns
            or int(row["device"]) != identity.device
            or int(row["inode"]) != identity.inode
        ):
            changed.append(identity)
    if changed:
        _upsert_cache_many(
            paths.db_file,
            [_scan_one(identity, folder, paths) for identity in changed],
        )
        refreshed = build_preview(
            paths.db_file,
            folder,
            location=normalize_location(job.get("batch_location")),
        )
        _update_job(
            paths.db_file,
            str(job["job_id"]),
            stage="Source changed after Preview",
            preview_json=json.dumps(refreshed, sort_keys=True, separators=(",", ":")),
            warnings_json=json.dumps(refreshed["warnings"], ensure_ascii=False),
        )
        raise ImportV0130Error(
            f"{len(changed)} source photograph(s) changed after Preview. Only those files were rescanned; confirm the refreshed Preview before importing."
        )

    corrections = _corrections(paths.db_file, folder)
    rows.sort(
        key=lambda row: (
            str(row.get("captured_at") or ""),
            str(row.get("original_name") or "").casefold(),
            str(row.get("source_path") or "").casefold(),
        )
    )
    full_hash_count = 0
    records_by_path: dict[str, PhotoRecord] = {}
    all_records: list[PhotoRecord] = []
    with db.transaction(paths.db_file) as connection:
        for index, row in enumerate(rows):
            path = Path(str(row["source_path"]))
            sha = str(row.get("sha256") or "")
            if not sha:
                sha = _hash_file(path)
                full_hash_count += 1
                connection.execute(
                    "UPDATE import_photo_cache SET sha256=? WHERE source_path=?",
                    (sha, str(path)),
                )
            record = PhotoRecord(
                path=path,
                original_name=str(row["original_name"]),
                captured_at=datetime.fromisoformat(str(row["captured_at"])),
                timestamp_source=str(row["timestamp_source"]),
                stream_index=index,
                sha256=sha,
                qr_payload=str(row.get("qr_payload") or "") or None,
            )
            records_by_path[str(path)] = record
            all_records.append(record)

    items: list[ItemRecord] = []
    command_records: list[PhotoRecord] = []
    for item_payload in preview["items"]:
        photos = [records_by_path[str(photo["source_path"])] for photo in item_payload["photos"]]
        items.append(
            ItemRecord(
                sequence=int(item_payload["sequence"]),
                shelf=normalize_location(job.get("batch_location")) or "UNASSIGNED",
                photos=photos,
            )
        )
    for row in rows:
        kind = _effective_kind(row, corrections.get(str(row["source_path"])))
        if kind == "next" or str(row.get("classification")) == "legacy":
            command_records.append(records_by_path[str(row["source_path"])])

    digest = hashlib.sha256()
    for record in all_records:
        digest.update(f"{record.stream_index}\0{record.sha256}\0{record.original_name}\n".encode("utf-8"))
    digest.update(preview["metadata_fingerprint"].encode("ascii"))
    created = datetime.now()
    batch = BatchRecord(
        batch_id=make_batch_id(created, folder.name),
        source_folder=folder,
        created_at=created,
        source_fingerprint=digest.hexdigest(),
        capture_source="FOLDER_NEXT_ONLY",
        started=True,
        ended=True,
        items=items,
        commands=command_records,
        source_photos=all_records,
        warnings=list(preview["warnings"]),
    )
    return batch, full_hash_count


def start_commit(paths: DataPaths, job_id: str) -> None:
    db.initialize(paths.db_file, paths=paths)
    with db.transaction(paths.db_file) as connection:
        job = connection.execute(
            "SELECT status,result_batch_id FROM import_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if not job:
            raise ImportV0130Error("Import job was not found.")
        status = str(job["status"])
        if status == "IMPORTED" or str(job["result_batch_id"] or ""):
            return
        if status in {"COMMIT_QUEUED", "COMMITTING"}:
            return
        if status not in {"READY", "NEEDS_ATTENTION"}:
            raise ImportV0130Error("Preview is not ready to import.")
        connection.execute(
            """UPDATE import_jobs
                  SET status='COMMIT_QUEUED',stage='Import queued',error_message='',updated_at=?
                WHERE job_id=? AND status IN ('READY','NEEDS_ATTENTION')""",
            (_iso_now(), job_id),
        )
    if _job_is_active(job_id):
        return
    _mark_active(job_id, True)
    _EXECUTOR.submit(_run_commit, paths, job_id)


def _run_commit(paths: DataPaths, job_id: str) -> None:
    try:
        with db.transaction(paths.db_file) as connection:
            row = connection.execute(
                "SELECT status,result_batch_id FROM import_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None or str(row["status"]) == "IMPORTED" or str(row["result_batch_id"] or ""):
                return
            claimed = connection.execute(
                """UPDATE import_jobs
                      SET status='COMMITTING',stage='Verifying source files',
                          started_at=?,updated_at=?
                    WHERE job_id=? AND status='COMMIT_QUEUED'""",
                (_iso_now(), _iso_now(), job_id),
            )
            if claimed.rowcount != 1:
                return
        job = get_job(paths.db_file, job_id)
        if not job:
            return
        batch, full_hash_count = _materialize_batch(paths, job)
        _update_job(paths.db_file, job_id, full_hash_count=full_hash_count, stage="Preserving originals")

        def progress(stage: str, completed: int, total: int) -> None:
            _update_job(
                paths.db_file,
                job_id,
                stage=stage,
                processed_count=completed,
                total_count=total,
            )

        result = process_batch(
            batch.source_folder,
            paths=paths,
            batch_name=batch.source_folder.name,
            prepared_batch=batch,
            progress_callback=progress,
            staging_key=job_id,
        )
        location = normalize_location(job.get("batch_location"))
        with db.transaction(paths.db_file) as connection:
            connection.execute(
                """UPDATE batches SET display_name=?,source_folder_name=?,batch_location=?,
                       import_job_id=?,capture_source='FOLDER_NEXT_ONLY' WHERE batch_id=?""",
                (batch.source_folder.name, batch.source_folder.name, location, job_id, result.batch_id),
            )
            connection.execute(
                "UPDATE items SET location=?,shelf=? WHERE batch_id=?",
                (location, location or "", result.batch_id),
            )
        db.set_setting(paths.db_file, "active_batch", result.batch_id)
        _update_job(
            paths.db_file,
            job_id,
            status="IMPORTED",
            stage="Import complete",
            result_batch_id=result.batch_id,
            completed_at=_iso_now(),
            processed_count=result.product_photo_count + result.command_count,
            total_count=result.product_photo_count + result.command_count,
        )
    except ImportV0130Error as exc:
        _update_job(
            paths.db_file,
            job_id,
            status="NEEDS_ATTENTION",
            stage="Preview refreshed",
            error_message=str(exc),
            completed_at=_iso_now(),
        )
    except Exception as exc:
        _update_job(
            paths.db_file,
            job_id,
            status="FAILED",
            stage="Import failed",
            error_message=f"{type(exc).__name__}: {exc}",
            completed_at=_iso_now(),
        )
    finally:
        _mark_active(job_id, False)


def recover_jobs(paths: DataPaths) -> int:
    db.initialize(paths.db_file, paths=paths)
    with db.transaction(paths.db_file) as connection:
        rows = connection.execute(
            "SELECT job_id,status FROM import_jobs WHERE status IN ('QUEUED','RUNNING','COMMIT_QUEUED','COMMITTING')"
        ).fetchall()
        for row in rows:
            status = str(row["status"])
            resumed = "COMMIT_QUEUED" if status.startswith("COMMIT") else "QUEUED"
            connection.execute(
                "UPDATE import_jobs SET status=?,stage=?,updated_at=? WHERE job_id=?",
                (resumed, "Ready to resume after restart", _iso_now(), str(row["job_id"])),
            )
    for row in rows:
        job_id = str(row["job_id"])
        if str(row["status"]).startswith("COMMIT"):
            if not _job_is_active(job_id):
                _mark_active(job_id, True)
                _EXECUTOR.submit(_run_commit, paths, job_id)
        else:
            _submit_preview(paths, job_id)
    return len(rows)


def list_batch_folders(paths: DataPaths) -> list[dict[str, Any]]:
    db.initialize(paths.db_file, paths=paths)
    home = ensure_batch_home(paths)
    with db.connect(paths.db_file) as connection:
        imported = {
            str(Path(row["source_folder"]).resolve()): dict(row)
            for row in connection.execute(
                "SELECT batch_id,source_folder,status,display_name FROM batches"
            ).fetchall()
        }
        jobs = connection.execute(
            """SELECT j.* FROM import_jobs j
               JOIN (SELECT folder_path,MAX(created_at) created_at FROM import_jobs GROUP BY folder_path) latest
                 ON latest.folder_path=j.folder_path AND latest.created_at=j.created_at"""
        ).fetchall()
        latest_jobs = {str(row["folder_path"]): dict(row) for row in jobs}
    folders: list[dict[str, Any]] = []
    try:
        entries = list(os.scandir(home))
    except OSError:
        entries = []
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
            path = str(Path(entry.path).resolve())
        except OSError:
            continue
        imported_row = imported.get(path)
        job = latest_jobs.get(path)
        if imported_row:
            state = "Previously imported"
        elif job and str(job.get("status")) in {"QUEUED", "RUNNING", "COMMIT_QUEUED", "COMMITTING"}:
            state = "In progress"
        elif job and str(job.get("status")) in {"FAILED", "NEEDS_ATTENTION"}:
            state = "Needs attention"
        elif job and str(job.get("status")) == "READY":
            state = "Ready to resume"
        else:
            state = "New"
        folders.append(
            {
                "name": entry.name,
                "path": path,
                "state": state,
                "job_id": str(job.get("job_id") or "") if job else "",
                "batch_id": str(imported_row.get("batch_id") or "") if imported_row else "",
            }
        )
    folders.sort(key=lambda row: row["name"].casefold())
    return folders


def thumbnail_path(db_file: Path, cache_id: str) -> Path | None:
    if not re.fullmatch(r"[a-f0-9]{32}", cache_id):
        return None
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT thumbnail_path FROM import_photo_cache WHERE cache_id=? AND thumbnail_path<>''",
            (cache_id,),
        ).fetchone()
    if not row:
        return None
    candidate = Path(str(row["thumbnail_path"]))
    return candidate if candidate.is_file() else None


def update_batch_display_name(db_file: Path, batch_id: str, value: str) -> None:
    name = str(value or "").strip()
    if not name:
        raise ImportV0130Error("Batch display name cannot be blank.")
    if len(name) > 160:
        raise ImportV0130Error("Batch display name must be 160 characters or fewer.")
    with db.transaction(db_file) as connection:
        exists = connection.execute("SELECT 1 FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
        if not exists:
            raise ImportV0130Error("Batch was not found.")
        connection.execute("UPDATE batches SET display_name=? WHERE batch_id=?", (name, batch_id))
        connection.execute(
            """INSERT INTO operational_events(
                   occurred_at,severity,component,event_type,batch_id,status,outcome,
                   safe_summary,detail_json,process_marker,retention_class
               ) VALUES(?,'INFO','batch','batch.display_name_changed',?,'COMPLETE','UPDATED',?,?,?,'BUSINESS')""",
            (
                db.now(),
                batch_id,
                "Batch display name updated without changing the source folder or Batch ID.",
                json.dumps({"display_name": name}, sort_keys=True),
                f"pid:{os.getpid()}",
            ),
        )
