from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from snapims.catalog import db as catalog_db
from snapims.catalog.models import MovieCandidate
from snapims.catalog.normalization import normalize_title, strip_leading_article

API_URL = "https://en.wikipedia.org/w/api.php"
DEFAULT_USER_AGENT = "SnapIMS-SLMC/0.1.0 (Canada VHS local movie catalog)"
_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


class WikipediaError(RuntimeError):
    code = "WIKIPEDIA_ERROR"


class WikipediaRateLimit(WikipediaError):
    code = "RATE_LIMIT"


class WikipediaTimeout(WikipediaError):
    code = "TIMEOUT"


class WikipediaMalformedResponse(WikipediaError):
    code = "MALFORMED_RESPONSE"


Transport = Callable[[dict[str, str]], tuple[int, dict[str, Any], dict[str, str]]]


def _request_key(params: dict[str, str]) -> str:
    encoded = urlencode(sorted(params.items()))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clean_wiki_value(value: str) -> str:
    text = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    text = re.sub(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", "", text, flags=re.S | re.I)
    text = re.sub(r"\{\{(?:nowrap|small|ubl|unbulleted list|plainlist)\|", "", text, flags=re.I)
    text = text.replace("{{end plainlist}}", "")
    text = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    # The closing braces of an infobox may be appended to the final field
    # value by the line-oriented parser. They are markup, never metadata.
    text = re.sub(r"\s*\}\}\s*$", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;\n\t")


def _split_list(value: str) -> tuple[str, ...]:
    cleaned = value.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    cleaned = re.sub(r"\*+", "\n", cleaned)
    parts = re.split(r"\n|;|\s+and\s+", cleaned)
    output: list[str] = []
    for part in parts:
        item = _clean_wiki_value(part)
        if item and item not in output:
            output.append(item)
    return tuple(output[:20])


def _infobox_fields(wikitext: str) -> dict[str, str]:
    match = re.search(r"\{\{Infobox\s+(?:film|television)[\s\S]*?\n\}\}", wikitext, flags=re.I)
    source = match.group(0) if match else wikitext[:20000]
    fields: dict[str, str] = {}
    current_key = ""
    current: list[str] = []
    for line in source.splitlines():
        field_match = re.match(r"\s*\|\s*([\w ]+)\s*=\s*(.*)$", line)
        if field_match:
            if current_key:
                fields[current_key] = "\n".join(current).strip()
            current_key = field_match.group(1).strip().casefold().replace(" ", "_")
            current = [field_match.group(2)]
        elif current_key:
            current.append(line)
    if current_key:
        fields[current_key] = "\n".join(current).strip()
    return fields


def _first_year(*values: str) -> int | None:
    for value in values:
        years = re.findall(r"(?<!\d)(18[789]\d|19\d{2}|20\d{2}|21\d{2})(?!\d)", value or "")
        if years:
            return int(years[0])
    return None


def _runtime_minutes(value: str) -> int | None:
    hour_match = re.search(r"(\d+)\s*hours?", value, flags=re.I)
    minute_match = re.search(r"(\d+)\s*(?:minutes?|mins?)", value, flags=re.I)
    if hour_match:
        return int(hour_match.group(1)) * 60 + (int(minute_match.group(1)) if minute_match else 0)
    if minute_match:
        return int(minute_match.group(1))
    number = re.search(r"\b(\d{2,3})\b", value or "")
    return int(number.group(1)) if number else None


def _canonical_title(page_title: str, infobox_name: str) -> str:
    if infobox_name:
        cleaned = _clean_wiki_value(infobox_name)
        if cleaned:
            return cleaned
    return re.sub(
        r"\s*\((?:\d{4}\s+)?(?:film|television film|TV film|miniseries|TV series)\)\s*$",
        "",
        page_title,
        flags=re.I,
    ).strip()


def _media_type(page_title: str, extract: str, categories: tuple[str, ...], wikitext: str) -> str:
    joined = " ".join((page_title, extract, " ".join(categories[:40]), wikitext[:1000])).casefold()
    if "miniseries" in joined or "television series" in joined or "tv series" in joined:
        return "television"
    if "television film" in joined or "tv film" in joined:
        return "television film"
    if (
        " film" in joined
        or "films" in joined
        or "infobox film" in joined
        or re.search(r"\(\d{4} film\)", page_title, flags=re.I)
    ):
        return "film"
    if any(term in joined for term in ("album", "song", "novel", "book", "company", "person", "episode")):
        return "non-film"
    return "unknown"


def _genres_from_categories(categories: tuple[str, ...]) -> tuple[str, ...]:
    genres: list[str] = []
    for category in categories:
        match = re.search(r"\b([A-Za-z -]+?) films\b", category)
        if not match:
            continue
        value = match.group(1).strip().casefold()
        if value in {"american", "british", "canadian", "english-language", "independent", "short", "silent"}:
            continue
        display = value.title()
        if display and display not in genres:
            genres.append(display)
    return tuple(genres[:10])


class FixtureTransport:
    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, params: dict[str, str]) -> tuple[int, dict[str, Any], dict[str, str]]:
        if params.get("list") == "search":
            title = params.get("srsearch", "").split(" film", 1)[0].replace('intitle:"', "").rstrip('"').strip()
            name = re.sub(r"[^a-z0-9]+", "-", normalize_title(title)).strip("-") or "empty"
            path = self.root / f"search-{name}.json"
        else:
            page_id = params.get("pageids") or params.get("pageid") or params.get("page") or "unknown"
            action = params.get("action", "query")
            path = self.root / f"{action}-{page_id}.json"
        if not path.is_file():
            return 200, {"query": {"search": [], "pages": []}}, {}
        return 200, json.loads(path.read_text(encoding="utf-8")), {}


class WikipediaClient:
    def __init__(
        self,
        catalog_db_file: Path,
        *,
        transport: Transport | None = None,
        user_agent: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        min_interval: float | None = None,
    ) -> None:
        self.catalog_db_file = catalog_db_file
        fixture = os.getenv("SNAPIMS_WIKIPEDIA_FIXTURE_DIR", "").strip()
        self.transport = transport or (FixtureTransport(Path(fixture)) if fixture else self._http_transport)
        self.user_agent = user_agent or os.getenv("SNAPIMS_WIKIPEDIA_USER_AGENT", DEFAULT_USER_AGENT)
        self.timeout = timeout if timeout is not None else float(
            catalog_db.get_setting(catalog_db_file, "wikipedia_timeout_seconds", "10")
        )
        self.max_retries = max_retries if max_retries is not None else int(
            catalog_db.get_setting(catalog_db_file, "wikipedia_max_retries", "2")
        )
        self.min_interval = min_interval if min_interval is not None else float(
            catalog_db.get_setting(catalog_db_file, "wikipedia_min_interval_seconds", "1.0")
        )

    def _rate_limit(self) -> None:
        global _LAST_REQUEST_AT
        with _LOCK:
            elapsed = time.monotonic() - _LAST_REQUEST_AT
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            _LAST_REQUEST_AT = time.monotonic()

    def _http_transport(self, params: dict[str, str]) -> tuple[int, dict[str, Any], dict[str, str]]:
        self._rate_limit()
        url = API_URL + "?" + urlencode(params)
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read()
                status = int(response.status)
                headers = {key.casefold(): value for key, value in response.headers.items()}
        except HTTPError as exc:
            if exc.code == 429:
                raise WikipediaRateLimit("Wikipedia rate limit reached") from exc
            raise WikipediaError(f"Wikipedia HTTP error {exc.code}") from exc
        except TimeoutError as exc:
            raise WikipediaTimeout("Wikipedia request timed out") from exc
        except URLError as exc:
            if "timed out" in str(exc).casefold():
                raise WikipediaTimeout("Wikipedia request timed out") from exc
            raise WikipediaError(f"Wikipedia network error: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WikipediaMalformedResponse("Wikipedia returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise WikipediaMalformedResponse("Wikipedia returned a non-object response")
        return status, payload, headers

    def request(self, params: dict[str, str], *, cache_seconds: int = 86400) -> dict[str, Any]:
        catalog_db.initialize(self.catalog_db_file)
        request_params = {"format": "json", "formatversion": "2", **params}
        key = _request_key(request_params)
        with catalog_db.connect(self.catalog_db_file, readonly=True) as connection:
            cached = connection.execute(
                "SELECT response_json,expires_at FROM wikipedia_response_cache WHERE cache_key=?", (key,)
            ).fetchone()
        if cached:
            expires_at = str(cached[1] or "")
            if not expires_at or datetime.fromisoformat(expires_at) > datetime.now().astimezone():
                return json.loads(str(cached[0]))

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                status, payload, headers = self.transport(request_params)
                if status == 429:
                    raise WikipediaRateLimit("Wikipedia rate limit reached")
                if status >= 500:
                    raise WikipediaError(f"Wikipedia server error {status}")
                if "error" in payload:
                    code = str((payload.get("error") or {}).get("code") or "")
                    if "ratelimit" in code:
                        raise WikipediaRateLimit("Wikipedia rate limit reached")
                    raise WikipediaError(f"Wikipedia API error: {code}")
                response_hash = _json_hash(payload)
                expires = (datetime.now().astimezone() + timedelta(seconds=cache_seconds)).isoformat(timespec="seconds")
                with catalog_db.transaction(self.catalog_db_file) as connection:
                    connection.execute(
                        """INSERT INTO wikipedia_response_cache(
                               cache_key,request_url,response_json,response_hash,http_status,retrieved_at,
                               expires_at,etag,last_modified
                           ) VALUES(?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(cache_key) DO UPDATE SET
                               response_json=excluded.response_json,response_hash=excluded.response_hash,
                               http_status=excluded.http_status,retrieved_at=excluded.retrieved_at,
                               expires_at=excluded.expires_at,etag=excluded.etag,last_modified=excluded.last_modified""",
                        (
                            key,
                            API_URL + "?" + urlencode(request_params),
                            json.dumps(payload, ensure_ascii=False),
                            response_hash,
                            status,
                            catalog_db.now(),
                            expires,
                            headers.get("etag", ""),
                            headers.get("last-modified", ""),
                        ),
                    )
                return payload
            except (WikipediaError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.max_retries or isinstance(exc, WikipediaRateLimit):
                    raise
                time.sleep(min(2**attempt, 4))
        assert last_error is not None
        raise last_error

    def search(self, title: str, year: int | None = None, *, limit: int = 5) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, 5))
        query = f'intitle:"{title.strip()}" film'
        if year:
            query += f" {year}"
        payload = self.request(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": "0",
                "srlimit": str(bounded),
                "srprop": "snippet|titlesnippet|sectiontitle|wordcount|timestamp",
            },
            cache_seconds=86400,
        )
        results = (payload.get("query") or {}).get("search") or []
        return [row for row in results if isinstance(row, dict)][:bounded]

    def fetch_candidate(self, page_id: str, *, query_title: str, query_year: int | None) -> MovieCandidate:
        detail = self.request(
            {
                "action": "query",
                "pageids": str(page_id),
                "redirects": "1",
                "prop": "info|extracts|pageprops|revisions|categories",
                "inprop": "url",
                "exintro": "1",
                "explaintext": "1",
                "rvprop": "ids|timestamp",
                "cllimit": "100",
            },
            cache_seconds=604800,
        )
        pages = (detail.get("query") or {}).get("pages") or []
        if not pages:
            raise WikipediaMalformedResponse(f"Wikipedia page {page_id} was not returned")
        page = pages[0]
        page_title = str(page.get("title") or "")
        extract = str(page.get("extract") or "").strip()
        categories = tuple(
            str(row.get("title") or "").removeprefix("Category:")
            for row in (page.get("categories") or [])
            if isinstance(row, dict)
        )
        parse = self.request(
            {"action": "parse", "pageid": str(page_id), "prop": "wikitext|categories"},
            cache_seconds=604800,
        )
        parse_data = parse.get("parse") or {}
        wikitext_value = parse_data.get("wikitext") or ""
        if isinstance(wikitext_value, dict):
            wikitext = str(wikitext_value.get("*") or "")
        else:
            wikitext = str(wikitext_value)
        fields = _infobox_fields(wikitext)
        canonical = _canonical_title(page_title, fields.get("name", ""))
        release_year = _first_year(fields.get("released", ""), page_title, extract)
        media_type = _media_type(page_title, extract, categories, wikitext)
        directors = _split_list(fields.get("director", ""))
        countries = _split_list(fields.get("country", ""))
        languages = _split_list(fields.get("language", ""))
        genres = _genres_from_categories(categories)
        revision = ""
        revisions = page.get("revisions") or []
        if revisions and isinstance(revisions[0], dict):
            revision = str(revisions[0].get("revid") or "")
        redirects = (detail.get("query") or {}).get("redirects") or []
        aliases = tuple(
            str(row.get("from") or "") for row in redirects if isinstance(row, dict) and row.get("from")
        )
        raw = {"detail": detail, "parse": parse}
        raw_hash = _json_hash(raw)
        candidate = MovieCandidate(
            provider="wikipedia",
            source_page_id=str(page.get("pageid") or page_id),
            source_page_title=page_title,
            source_url=str(page.get("fullurl") or f"https://en.wikipedia.org/?curid={page_id}"),
            canonical_title=canonical,
            original_title=_clean_wiki_value(fields.get("original_name", "")),
            release_year=release_year,
            release_date=_clean_wiki_value(fields.get("released", "")) or None,
            media_type=media_type,
            runtime_minutes=_runtime_minutes(fields.get("runtime", "")),
            countries=countries,
            languages=languages,
            directors=directors,
            genres=genres,
            summary=extract[:1200],
            aliases=aliases,
            source_revision_id=revision,
            retrieved_at=catalog_db.now(),
            raw_response_hash=raw_hash,
            attribution="English Wikipedia; page link and revision retained; text reuse subject to CC BY-SA",
            parser_version=catalog_db.CATALOG_PARSER_VERSION,
            raw=raw,
        )
        return replace(candidate, **self._rank(candidate, query_title, query_year))

    def _rank(self, candidate: MovieCandidate, query_title: str, query_year: int | None) -> dict[str, Any]:
        evidence: list[str] = []
        score = 0.0
        expected = normalize_title(query_title)
        actual = normalize_title(candidate.canonical_title)
        if actual == expected:
            score += 0.62
            evidence.append("exact normalized title")
        elif strip_leading_article(actual) == strip_leading_article(expected):
            score += 0.56
            evidence.append("title differs only by leading article")
        elif expected and (expected in actual or actual in expected):
            score += 0.34
            evidence.append("partial title agreement")
        if query_year is not None and candidate.release_year is not None:
            if query_year == candidate.release_year:
                score += 0.25
                evidence.append("release year agrees")
            elif abs(query_year - candidate.release_year) <= 1:
                score += 0.10
                evidence.append("release year is within one year")
            else:
                score -= 0.35
                evidence.append("release year conflicts")
        elif candidate.release_year is not None:
            score += 0.03
            evidence.append("candidate has a release year")
        if candidate.media_type == "film":
            score += 0.12
            evidence.append("page is classified as a film")
        elif candidate.media_type == "television film":
            score += 0.04
            evidence.append("page is a television film")
        elif candidate.media_type in {"television", "non-film"}:
            score -= 0.30
            evidence.append(f"page is classified as {candidate.media_type}")
        rejected = ""
        if candidate.media_type == "non-film":
            rejected = "Page is not a film"
        return {"score": max(0.0, min(score, 1.0)), "evidence": tuple(evidence), "rejected_reason": rejected}

    def search_candidates(self, title: str, year: int | None = None, *, limit: int = 5) -> list[MovieCandidate]:
        results = self.search(title, year, limit=limit)
        candidates: list[MovieCandidate] = []
        for result in results:
            page_id = result.get("pageid")
            if page_id is None:
                continue
            candidates.append(self.fetch_candidate(str(page_id), query_title=title, query_year=year))
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates
