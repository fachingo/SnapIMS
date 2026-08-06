#!/usr/bin/env python3
"""Deterministic SnapIMS v0.15.0 Import benchmark with real QR images."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil
import qrcode
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from snapims import db
from snapims.config import DataPaths
from snapims.import_v0130 import NEXT_PAYLOAD, get_job, start_commit, start_preview


def product(path: Path, label: str) -> None:
    image = Image.new("RGB", (1200, 900), (52, 83, 111))
    ImageDraw.Draw(image).text((55, 55), label, fill="white")
    image.save(path, quality=88)


def qr(path: Path, payload: str) -> None:
    code = qrcode.make(payload).convert("RGB").resize((620, 620))
    image = Image.new("RGB", (1200, 900), "white")
    image.paste(code, ((1200 - 620) // 2, (900 - 620) // 2))
    image.save(path, quality=92)


def make_fixture(folder: Path, items: int, legacy: bool = True) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    index = 0
    if legacy:
        for payload, label in [
            ("CVHS1:BATCH:START", "start"),
            ("CVHS1:LOC:A6", "location"),
        ]:
            qr(folder / f"{index:04d}-{label}.jpg", payload); index += 1
    for item in range(items):
        product(folder / f"{index:04d}-tape-{item+1:03d}.jpg", f"TAPE {item+1}"); index += 1
        if item < items - 1:
            qr(folder / f"{index:04d}-next-{item+1:03d}.jpg", NEXT_PAYLOAD); index += 1
    if legacy:
        qr(folder / f"{index:04d}-end.jpg", "CVHS1:BATCH:END"); index += 1
    return index


def wait(paths: DataPaths, job_id: str, terminal: set[str], timeout: float = 120) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = get_job(paths.db_file, job_id)
        if job and job["status"] in terminal:
            return job
        time.sleep(0.01)
    raise RuntimeError(f"job timed out: {get_job(paths.db_file, job_id)}")


def preview(paths: DataPaths, folder: Path, location: str = "A6") -> tuple[float, dict]:
    started = time.perf_counter()
    job_id = start_preview(paths, folder, location=location)
    returned_ms = (time.perf_counter() - started) * 1000
    job = wait(paths, job_id, {"READY", "NEEDS_ATTENTION", "FAILED"})
    if job["status"] == "FAILED":
        raise RuntimeError(job["error_message"])
    return returned_ms, job


def baseline_parse(baseline_root: Path, fixture: Path) -> dict:
    code = r'''
import json, resource, sys, time, types
from pathlib import Path
stub=types.ModuleType("pillow_heif")
stub.register_heif_opener=lambda: None
sys.modules.setdefault("pillow_heif", stub)
sys.path.insert(0, sys.argv[1])
from snapims.pipeline import parse_batch
fixture=Path(sys.argv[2])
values=[]
for _ in range(2):
    t=time.perf_counter(); batch=parse_batch(fixture, manual_location="A6", override_locations=True); values.append((time.perf_counter()-t)*1000)
print(json.dumps({"runs_ms":values,"item_count":len(batch.items),"max_rss_kb":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
'''
    result = subprocess.run(
        [sys.executable, "-c", code, str(baseline_root), str(fixture)],
        check=True, capture_output=True, text=True, timeout=180,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--typical-fixture", type=Path, help="Existing 40-60 photo fixture copied without modification")
    args = parser.parse_args()
    workspace = Path(tempfile.mkdtemp(prefix="snapims-v0150-benchmark-"))
    try:
        paths = DataPaths.from_root(workspace / "data").ensure()
        db.initialize(paths.db_file, paths=paths)
        typical = paths.batches / "AUGUST-HORROR-01"
        synthetic = paths.batches / "SYNTHETIC-100"
        if args.typical_fixture:
            shutil.copytree(args.typical_fixture.resolve(), typical)
            typical_count = len([path for path in typical.iterdir() if path.is_file()])
        else:
            typical_count = make_fixture(typical, 20, legacy=True)  # 42 files
        synthetic_count = make_fixture(synthetic, 100, legacy=True)  # 202 files

        process = psutil.Process()
        rss_before = process.memory_info().rss
        typical_return_ms, typical_cold = preview(paths, typical)
        rss_after_typical = process.memory_info().rss
        warm_return_ms, typical_warm = preview(paths, typical, "Processing Table")

        synthetic_return_ms, synthetic_cold = preview(paths, synthetic)
        rss_after_synthetic = process.memory_info().rss
        _, synthetic_warm = preview(paths, synthetic, "None")

        commit_job_id = start_preview(paths, typical, location="Processing Table")
        ready = wait(paths, commit_job_id, {"READY", "NEEDS_ATTENTION", "FAILED"})
        commit_start = time.perf_counter()
        start_commit(paths, commit_job_id)
        committed = wait(paths, commit_job_id, {"IMPORTED", "FAILED", "NEEDS_ATTENTION"})
        commit_ms = (time.perf_counter() - commit_start) * 1000
        if committed["status"] != "IMPORTED":
            raise RuntimeError(committed["error_message"])

        baseline = None
        if args.baseline_root:
            baseline = baseline_parse(args.baseline_root.resolve(), typical)

        cold_ms = typical_cold["duration_ms"]
        baseline_ms = baseline["runs_ms"][0] if baseline else None
        improvement = ((baseline_ms - cold_ms) / baseline_ms * 100) if baseline_ms else None
        result = {
            "environment": {
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "cpu_count": os.cpu_count(),
                "actual_target_mac_available": False,
            },
            "typical_20_item_42_photo": {
                "files": typical_count,
                "preview_request_return_ms": round(typical_return_ms, 3),
                "cold_preview_ms": cold_ms,
                "warm_preview_ms": typical_warm["duration_ms"],
                "cold_decodes": typical_cold["decode_count"],
                "cold_qr_scans": typical_cold["qr_scan_count"],
                "warm_decodes": typical_warm["decode_count"],
                "warm_qr_scans": typical_warm["qr_scan_count"],
                "warm_cache_hits": typical_warm["cache_hits"],
                "location_only_request_return_ms": round(warm_return_ms, 3),
                "commit_ms": round(commit_ms, 3),
                "full_hashes_at_commit": committed["full_hash_count"],
            },
            "synthetic_100_item_202_photo": {
                "files": synthetic_count,
                "preview_request_return_ms": round(synthetic_return_ms, 3),
                "cold_preview_ms": synthetic_cold["duration_ms"],
                "warm_preview_ms": synthetic_warm["duration_ms"],
                "cold_decodes": synthetic_cold["decode_count"],
                "cold_qr_scans": synthetic_cold["qr_scan_count"],
                "warm_decodes": synthetic_warm["decode_count"],
                "warm_qr_scans": synthetic_warm["qr_scan_count"],
                "warm_cache_hits": synthetic_warm["cache_hits"],
            },
            "memory": {
                "rss_before_mb": round(rss_before / 1024 / 1024, 2),
                "rss_after_typical_mb": round(rss_after_typical / 1024 / 1024, 2),
                "rss_after_synthetic_mb": round(rss_after_synthetic / 1024 / 1024, 2),
                "observed_peak_proxy_mb": round(max(rss_after_typical, rss_after_synthetic) / 1024 / 1024, 2),
            },
            "baseline_v0.12.3": baseline,
            "cold_preview_improvement_percent": round(improvement, 2) if improvement is not None else None,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
