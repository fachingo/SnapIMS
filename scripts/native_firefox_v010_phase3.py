from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from playwright.sync_api import ConsoleMessage, Error, sync_playwright

from snapims.auth import generate_secret, hash_password
from snapims.config import DataPaths
from snapims.settings import ConfigurationService

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "v0.10.0" / "phase-3-firefox"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_health(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(
                "SnapIMS Phase 3 browser server exited before health passed:\n"
                + output
            )
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("SnapIMS Phase 3 browser server did not become healthy")


def start_server(
    data_dir: Path,
    environment: dict[str, str],
    url: str,
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "snapims.cli",
            "--data-dir",
            str(data_dir),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            url.rsplit(":", 1)[-1],
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    wait_for_health(url, process)
    return process


def stop_server(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="snapims-v010-phase3-firefox-"))
    data_dir = workspace / "data"
    paths = DataPaths.from_root(data_dir).ensure()
    fixture_dir = ROOT / "tests" / "fixtures" / "wikipedia"
    administrator_password = secrets.token_urlsafe(24)
    stored_provider_secret = "browser-fixture-" + secrets.token_urlsafe(24)

    environment = os.environ.copy()
    for key in (
        "SNAPIMS_AUTH_SECRET",
        "SNAPIMS_ADMIN_PASSWORD_HASH",
        "SNAPIMS_ADMIN_USERNAME",
        "SNAPIMS_SESSION_GENERATION",
        "OPENAI_API_KEY",
        "SHOPIFY_ADMIN_ACCESS_TOKEN",
    ):
        environment.pop(key, None)
    environment.update(
        {
            "SNAPIMS_SKIP_DOTENV": "1",
            "SNAPIMS_PROJECT_PATH": str(ROOT),
            "SNAPIMS_DATA_DIR": str(data_dir),
            "SNAPIMS_WIKIPEDIA_FIXTURE_DIR": str(fixture_dir),
            "SHOPIFY_DRAFT_ONLY": "true",
            "CLOUDFLARE_TUNNEL_CONFIG": str(
                workspace / "missing-cloudflared.yml"
            ),
        }
    )
    service = ConfigurationService(
        project_path=ROOT,
        paths=paths,
        process_environment=environment,
        legacy={},
    )
    service.save_secrets(
        "security",
        {
            "SNAPIMS_AUTH_SECRET": generate_secret(),
            "SNAPIMS_ADMIN_PASSWORD_HASH": hash_password(
                administrator_password
            ),
        },
    )
    service.save_nonsecret(
        "security",
        {
            "SNAPIMS_ADMIN_USERNAME": "admin",
            "SNAPIMS_SESSION_GENERATION": "1",
        },
    )

    url = f"http://127.0.0.1:{free_port()}"
    server = start_server(data_dir, environment, url)
    console_errors: list[str] = []
    page_errors: list[str] = []
    results: dict[str, Any] = {
        "browser": "Playwright Firefox",
        "url": url,
        "workspace": str(workspace),
        "checks": {},
        "console_errors": console_errors,
        "page_errors": page_errors,
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1600, "height": 1100},
                accept_downloads=True,
            )
            page = context.new_page()

            def record_console(message: ConsoleMessage) -> None:
                if message.type == "error":
                    console_errors.append(message.text)

            def record_page_error(error: Error) -> None:
                page_errors.append(str(error))

            page.on("console", record_console)
            page.on("pageerror", record_page_error)

            page.goto(f"{url}/login", wait_until="networkidle")
            page.get_by_label("Username").fill("admin")
            page.get_by_label("Password").fill(administrator_password)
            page.get_by_role("button", name="Log in").click()
            page.wait_for_url(f"{url}/")
            results["checks"]["stored_auth_login"] = True

            page.goto(f"{url}/settings", wait_until="networkidle")
            settings_source = page.content()
            expected_sections = (
                "General",
                "Recognition",
                "Shopify",
                "Movie Data",
                "Infrastructure",
                "Security",
                "Backup and Retention",
            )
            results["checks"]["all_settings_sections"] = all(
                heading in settings_source for heading in expected_sections
            )
            results["checks"]["provenance_and_external_override"] = (
                "Source: environment" in settings_source
                and "externally managed" in settings_source
            )
            results["checks"]["security_secrets_not_rendered"] = (
                administrator_password not in settings_source
                and stored_provider_secret not in settings_source
            )
            page.screenshot(
                path=EVIDENCE / "01-secure-settings.png",
                full_page=True,
            )

            secret_form = page.locator(
                'form[action="/settings/recognition/secrets"]'
            )
            secret_form.locator('[name="OPENAI_API_KEY"]').fill(
                stored_provider_secret
            )
            secret_form.locator('[name="current_password"]').fill(
                administrator_password
            )
            secret_form.get_by_role(
                "button", name="Save OpenAI key securely"
            ).click()
            page.wait_for_url(f"{url}/settings?message=*")
            results["checks"]["secret_save_never_echoes"] = (
                stored_provider_secret not in page.content()
                and stored_provider_secret not in page.url
            )

            page.goto(f"{url}/settings#movie", wait_until="networkidle")
            movie_test = page.locator('form[action="/settings/movie/test"]')
            movie_test.locator(
                '[name="SNAPIMS_WIKIPEDIA_USER_AGENT"]'
            ).fill("SnapIMS/0.10 browser acceptance https://example.invalid/contact")
            movie_test.locator('[name="candidate_title"]').fill("The Thing")
            movie_test.locator('[name="candidate_year"]').fill("1982")
            movie_test.get_by_role(
                "button", name="Test candidate search and provenance"
            ).click()
            page.get_by_text(
                "Candidate provenance preview", exact=True
            ).wait_for()
            results["checks"]["movie_candidate_provenance"] = (
                "The Thing" in page.content()
                and "Wikipedia returned" in page.content()
            )
            page.screenshot(
                path=EVIDENCE / "02-movie-candidate-test.png",
                full_page=True,
            )

            page.goto(f"{url}/diagnostics", wait_until="networkidle")
            with page.expect_download() as download_info:
                page.get_by_role(
                    "button", name="Export support bundle"
                ).click()
            bundle = EVIDENCE / "support-bundle.zip"
            download_info.value.save_as(bundle)
            with zipfile.ZipFile(bundle) as archive:
                bundle_content = b"\n".join(
                    archive.read(name) for name in archive.namelist()
                )
            results["checks"]["support_bundle_omits_secret"] = (
                stored_provider_secret.encode() not in bundle_content
                and administrator_password.encode() not in bundle_content
            )

            stop_server(server)
            server = start_server(data_dir, environment, url)
            page.goto(f"{url}/settings", wait_until="networkidle")
            results["checks"]["secret_retained_after_restart"] = (
                "Configured — enter a replacement" in page.content()
                and "Source: secret store" in page.content()
                and stored_provider_secret not in page.content()
            )

            revoke_form = page.locator(
                'form[action="/settings/security/revoke"]'
            )
            revoke_form.locator('[name="current_password"]').fill(
                administrator_password
            )
            revoke_form.get_by_role("button", name="Revoke all sessions").click()
            page.wait_for_url(f"{url}/login?error=*")
            results["checks"]["session_revocation"] = True
            browser.close()
    finally:
        if server.poll() is None:
            stop_server(server)

    secret_file_content = service.secret_file.read_text(encoding="utf-8")
    results["checks"]["owner_only_secret_store"] = (
        service.paths.secrets.stat().st_mode & 0o777 == 0o700
        and service.secret_file.stat().st_mode & 0o777 == 0o600
        and stored_provider_secret in secret_file_content
    )
    checks = results["checks"]
    results["passed"] = (
        all(checks.values())
        and not results["console_errors"]
        and not results["page_errors"]
    )
    (EVIDENCE / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not results["passed"]:
        raise SystemExit(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
