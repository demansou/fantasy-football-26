"""Fantasy Football Calculator ADP ingestion with immutable provenance.

Fantasy Football Calculator is a market-price source, not a projection source.
This adapter therefore emits normalized ADP records instead of constructing
``PlayerProjection`` objects with invented fantasy-point estimates.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SOURCE_ID = "fantasy_football_calculator"
SOURCE_NAME = "Fantasy Football Calculator"
API_ROOT = "https://fantasyfootballcalculator.com/api/v1/adp"
DOCUMENTATION_URL = "https://help.fantasyfootballcalculator.com/article/42-adp-rest-api"
METHODOLOGY_URL = (
    "https://help.fantasyfootballcalculator.com/article/34-average-draft-position-adp-data"
)
ADAPTER_VERSION = "1.0.0"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
MAX_RESPONSE_BYTES = 5_000_000

SCORING_LABELS = {
    "standard": "Non-PPR",
    "half-ppr": "Half-PPR",
    "ppr": "PPR",
}
POSITION_MAP = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "PK": "K",
    "K": "K",
    "DEF": "DST",
    "DST": "DST",
    "D/ST": "DST",
}
NORMALIZED_FIELDS = (
    "source",
    "source_player_id",
    "name",
    "position",
    "team",
    "bye_week",
    "adp",
    "adp_formatted",
    "times_drafted",
    "high_pick",
    "low_pick",
    "adp_stdev",
    "season",
    "teams",
    "scoring",
    "source_window_start",
    "source_window_end",
    "retrieved_at",
)


class FfcSourceError(RuntimeError):
    """Raised when FFC cannot be fetched or violates the adapter contract."""


@dataclass(frozen=True)
class FfcAdpQuery:
    """A reproducible Fantasy Football Calculator ADP query."""

    season: int
    teams: int = 10
    scoring: str = "ppr"

    def __post_init__(self) -> None:
        if isinstance(self.season, bool) or not isinstance(self.season, int):
            raise ValueError("FFC season must be an integer")
        if not 2007 <= self.season <= 2100:
            raise ValueError("FFC season must be between 2007 and 2100")
        if isinstance(self.teams, bool) or not isinstance(self.teams, int):
            raise ValueError("FFC team count must be an integer")
        if not 4 <= self.teams <= 20:
            raise ValueError("FFC team count must be between 4 and 20")
        if self.scoring not in SCORING_LABELS:
            choices = ", ".join(SCORING_LABELS)
            raise ValueError(f"FFC scoring must be one of: {choices}")

    @property
    def url(self) -> str:
        query = urlencode({"teams": self.teams, "year": self.season})
        return f"{API_ROOT}/{self.scoring}?{query}"


@dataclass(frozen=True)
class FfcAdpRecord:
    source_player_id: str
    name: str
    position: str
    team: str
    bye_week: int
    adp: float
    adp_formatted: str
    times_drafted: int
    high_pick: int
    low_pick: int
    adp_stdev: float


@dataclass(frozen=True)
class FfcAdpSnapshot:
    query: FfcAdpQuery
    retrieved_at: datetime
    source_url: str
    source_type: str
    rounds: int
    total_drafts: int
    window_start: date
    window_end: date
    records: tuple[FfcAdpRecord, ...]
    source_fields: tuple[str, ...]
    raw_bytes: bytes
    response_last_modified: str | None = None
    response_etag: str | None = None

    @property
    def raw_sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()


def _required_string(mapping: Mapping[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FfcSourceError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _required_integer(
    mapping: Mapping[str, Any],
    key: str,
    context: str,
    *,
    minimum: int = 0,
) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FfcSourceError(f"{context}.{key} must be an integer >= {minimum}")
    return value


def _required_number(
    mapping: Mapping[str, Any],
    key: str,
    context: str,
    *,
    minimum: float = 0.0,
) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FfcSourceError(f"{context}.{key} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise FfcSourceError(f"{context}.{key} must be finite and >= {minimum}")
    return number


def _required_date(mapping: Mapping[str, Any], key: str, context: str) -> date:
    value = _required_string(mapping, key, context)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise FfcSourceError(f"{context}.{key} must use YYYY-MM-DD format") from error


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return value.astimezone(timezone.utc)


def parse_ffc_adp(
    payload: Any,
    query: FfcAdpQuery,
    *,
    retrieved_at: datetime,
    source_url: str | None = None,
    raw_bytes: bytes | None = None,
    response_last_modified: str | None = None,
    response_etag: str | None = None,
) -> FfcAdpSnapshot:
    """Validate and normalize a decoded FFC ADP response."""

    retrieved_at = _utc_timestamp(retrieved_at)
    if not isinstance(payload, Mapping):
        raise FfcSourceError("FFC response must contain a JSON object")
    if payload.get("status") != "Success":
        raise FfcSourceError(f"FFC response status was {payload.get('status')!r}, not 'Success'")

    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        raise FfcSourceError("FFC response.meta must contain an object")
    source_type = _required_string(meta, "type", "meta")
    expected_type = SCORING_LABELS[query.scoring]
    if source_type != expected_type:
        raise FfcSourceError(
            f"FFC returned scoring type {source_type!r}; expected {expected_type!r}"
        )
    teams = _required_integer(meta, "teams", "meta", minimum=1)
    if teams != query.teams:
        raise FfcSourceError(f"FFC returned {teams} teams; expected {query.teams}")
    rounds = _required_integer(meta, "rounds", "meta", minimum=1)
    total_drafts = _required_integer(meta, "total_drafts", "meta", minimum=0)
    window_start = _required_date(meta, "start_date", "meta")
    window_end = _required_date(meta, "end_date", "meta")
    if window_start > window_end:
        raise FfcSourceError("FFC source window starts after it ends")

    raw_players = payload.get("players")
    if not isinstance(raw_players, list) or not raw_players:
        raise FfcSourceError("FFC response.players must contain at least one player")

    records: list[FfcAdpRecord] = []
    seen_ids: set[str] = set()
    source_fields: set[str] = set()
    for index, player in enumerate(raw_players):
        context = f"players[{index}]"
        if not isinstance(player, Mapping):
            raise FfcSourceError(f"{context} must contain an object")
        source_fields.update(str(field) for field in player)

        raw_id = player.get("player_id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
            raise FfcSourceError(f"{context}.player_id must be an integer or string")
        source_player_id = str(raw_id).strip()
        if not source_player_id:
            raise FfcSourceError(f"{context}.player_id cannot be empty")
        if source_player_id in seen_ids:
            raise FfcSourceError(f"FFC returned duplicate player_id {source_player_id!r}")
        seen_ids.add(source_player_id)

        name = _required_string(player, "name", context)
        raw_position = _required_string(player, "position", context).upper()
        try:
            position = POSITION_MAP[raw_position]
        except KeyError as error:
            raise FfcSourceError(
                f"{context}.position {raw_position!r} is not supported"
            ) from error
        team = _required_string(player, "team", context).upper()
        bye_week = _required_integer(player, "bye", context, minimum=1)
        if bye_week > 18:
            raise FfcSourceError(f"{context}.bye must be between 1 and 18")
        adp = _required_number(player, "adp", context, minimum=0.01)
        adp_formatted = _required_string(player, "adp_formatted", context)
        times_drafted = _required_integer(player, "times_drafted", context, minimum=1)
        high_pick = _required_integer(player, "high", context, minimum=1)
        low_pick = _required_integer(player, "low", context, minimum=1)
        if high_pick > low_pick:
            raise FfcSourceError(f"{context}.high cannot be greater than low")
        adp_stdev = _required_number(player, "stdev", context, minimum=0.0)

        records.append(
            FfcAdpRecord(
                source_player_id=source_player_id,
                name=name,
                position=position,
                team=team,
                bye_week=bye_week,
                adp=adp,
                adp_formatted=adp_formatted,
                times_drafted=times_drafted,
                high_pick=high_pick,
                low_pick=low_pick,
                adp_stdev=adp_stdev,
            )
        )

    if raw_bytes is None:
        raw_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    return FfcAdpSnapshot(
        query=query,
        retrieved_at=retrieved_at,
        source_url=source_url or query.url,
        source_type=source_type,
        rounds=rounds,
        total_drafts=total_drafts,
        window_start=window_start,
        window_end=window_end,
        records=tuple(sorted(records, key=lambda record: (record.adp, record.source_player_id))),
        source_fields=tuple(sorted(source_fields)),
        raw_bytes=raw_bytes,
        response_last_modified=response_last_modified,
        response_etag=response_etag,
    )


def fetch_ffc_adp(
    query: FfcAdpQuery,
    *,
    timeout: float = 20.0,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> FfcAdpSnapshot:
    """Fetch one FFC response and return a validated in-memory snapshot."""

    if timeout <= 0:
        raise ValueError("FFC timeout must be positive")
    request = Request(
        query.url,
        headers={
            "Accept": "application/json",
            "User-Agent": "fantasy-football-26/0.1 (+personal draft research)",
        },
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            raw_bytes = response.read(MAX_RESPONSE_BYTES + 1)
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
    except HTTPError as error:
        raise FfcSourceError(f"FFC request failed with HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise FfcSourceError(f"FFC request failed: {error}") from error

    if len(raw_bytes) > MAX_RESPONSE_BYTES:
        raise FfcSourceError(
            f"FFC response exceeded the {MAX_RESPONSE_BYTES:,}-byte safety limit"
        )
    try:
        payload = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FfcSourceError("FFC returned invalid JSON") from error

    return parse_ffc_adp(
        payload,
        query,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        source_url=query.url,
        raw_bytes=raw_bytes,
        response_last_modified=last_modified,
        response_etag=etag,
    )


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalized_csv(snapshot: FfcAdpSnapshot) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=NORMALIZED_FIELDS, lineterminator="\n")
    writer.writeheader()
    retrieved_at = _iso_utc(snapshot.retrieved_at)
    for record in snapshot.records:
        writer.writerow(
            {
                "source": SOURCE_ID,
                "source_player_id": record.source_player_id,
                "name": record.name,
                "position": record.position,
                "team": record.team,
                "bye_week": record.bye_week,
                "adp": record.adp,
                "adp_formatted": record.adp_formatted,
                "times_drafted": record.times_drafted,
                "high_pick": record.high_pick,
                "low_pick": record.low_pick,
                "adp_stdev": record.adp_stdev,
                "season": snapshot.query.season,
                "teams": snapshot.query.teams,
                "scoring": snapshot.query.scoring,
                "source_window_start": snapshot.window_start.isoformat(),
                "source_window_end": snapshot.window_end.isoformat(),
                "retrieved_at": retrieved_at,
            }
        )
    return buffer.getvalue().encode("utf-8")


def _manifest(snapshot: FfcAdpSnapshot, normalized_bytes: bytes) -> dict[str, Any]:
    position_counts = dict(sorted(Counter(record.position for record in snapshot.records).items()))
    source_schema = json.dumps(snapshot.source_fields, separators=(",", ":")).encode("utf-8")
    source_age_days = (snapshot.retrieved_at.date() - snapshot.window_end).days
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "dataset": "average_draft_position",
        "source": {
            "id": SOURCE_ID,
            "name": SOURCE_NAME,
            "url": snapshot.source_url,
            "documentation_url": DOCUMENTATION_URL,
            "methodology_url": METHODOLOGY_URL,
            "attribution": "ADP data from Fantasy Football Calculator",
        },
        "query": {
            "season": snapshot.query.season,
            "teams": snapshot.query.teams,
            "scoring": snapshot.query.scoring,
        },
        "retrieved_at": _iso_utc(snapshot.retrieved_at),
        "source_snapshot": {
            "type": snapshot.source_type,
            "rounds": snapshot.rounds,
            "total_drafts": snapshot.total_drafts,
            "start_date": snapshot.window_start.isoformat(),
            "end_date": snapshot.window_end.isoformat(),
            "age_days_at_retrieval": source_age_days,
            "http_last_modified": snapshot.response_last_modified,
            "http_etag": snapshot.response_etag,
        },
        "quality": {
            "record_count": len(snapshot.records),
            "duplicate_source_ids": 0,
            "position_counts": position_counts,
            "source_fields": list(snapshot.source_fields),
            "source_schema_sha256": hashlib.sha256(source_schema).hexdigest(),
        },
        "artifacts": {
            "raw": {
                "path": "raw.json",
                "bytes": len(snapshot.raw_bytes),
                "sha256": snapshot.raw_sha256,
            },
            "normalized": {
                "path": "adp.csv",
                "bytes": len(normalized_bytes),
                "sha256": hashlib.sha256(normalized_bytes).hexdigest(),
                "fields": list(NORMALIZED_FIELDS),
            },
        },
        "warnings": [
            "This dataset contains market ADP only; it is not a fantasy-points projection."
        ],
    }


def write_ffc_snapshot(snapshot: FfcAdpSnapshot, output_root: str | Path) -> Path:
    """Atomically publish raw, normalized, and manifest artifacts without overwrite."""

    root = Path(output_root)
    parent = root / SOURCE_ID / "adp" / str(snapshot.query.season)
    parent.mkdir(parents=True, exist_ok=True)
    snapshot_name = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    destination = parent / snapshot_name
    if destination.exists():
        raise FileExistsError(f"snapshot already exists: {destination}")

    normalized_bytes = _normalized_csv(snapshot)
    manifest_bytes = (
        json.dumps(_manifest(snapshot, normalized_bytes), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "raw.json").write_bytes(snapshot.raw_bytes)
        (staging / "adp.csv").write_bytes(normalized_bytes)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        staging.rename(destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return destination
