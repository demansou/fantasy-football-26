import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.sources.ffc import (
    FfcAdpQuery,
    FfcSourceError,
    fetch_ffc_adp,
    parse_ffc_adp,
    write_ffc_snapshot,
)


def response_payload() -> dict[str, object]:
    return {
        "status": "Success",
        "meta": {
            "type": "PPR",
            "teams": 10,
            "rounds": 15,
            "total_drafts": 123,
            "start_date": "2026-08-27",
            "end_date": "2026-09-02",
        },
        "players": [
            {
                "player_id": 1002,
                "name": "Example Defense",
                "position": "DEF",
                "team": "EXA",
                "adp": 151.2,
                "adp_formatted": "16.01",
                "times_drafted": 80,
                "high": 130,
                "low": 170,
                "stdev": 8.4,
                "bye": 8,
            },
            {
                "player_id": 1001,
                "name": "Example Runner",
                "position": "RB",
                "team": "TST",
                "adp": 12.5,
                "adp_formatted": "2.03",
                "times_drafted": 120,
                "high": 4,
                "low": 25,
                "stdev": 4.2,
                "bye": 10,
            },
        ],
    }


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.headers = {
            "Last-Modified": "Wed, 02 Sep 2026 18:22:37 GMT",
            "ETag": '"fixture"',
        }

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class FfcSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = FfcAdpQuery(season=2026, teams=10, scoring="ppr")
        self.retrieved_at = datetime(2026, 9, 2, 18, 30, tzinfo=timezone.utc)

    def test_query_builds_documented_endpoint(self) -> None:
        self.assertEqual(
            self.query.url,
            "https://fantasyfootballcalculator.com/api/v1/adp/ppr?teams=10&year=2026",
        )
        with self.assertRaisesRegex(ValueError, "scoring"):
            FfcAdpQuery(season=2026, scoring="points-per-reception")

    def test_normalizes_source_positions_and_sorts_by_adp(self) -> None:
        snapshot = parse_ffc_adp(
            response_payload(),
            self.query,
            retrieved_at=self.retrieved_at,
        )

        self.assertEqual([record.source_player_id for record in snapshot.records], ["1001", "1002"])
        self.assertEqual(snapshot.records[1].position, "DST")
        self.assertEqual(snapshot.total_drafts, 123)
        self.assertIn("times_drafted", snapshot.source_fields)

    def test_rejects_query_mismatch_and_duplicate_ids(self) -> None:
        wrong_type = response_payload()
        wrong_type["meta"]["type"] = "Half-PPR"  # type: ignore[index]
        with self.assertRaisesRegex(FfcSourceError, "expected 'PPR'"):
            parse_ffc_adp(wrong_type, self.query, retrieved_at=self.retrieved_at)

        duplicates = response_payload()
        duplicates["players"][1]["player_id"] = 1002  # type: ignore[index]
        with self.assertRaisesRegex(FfcSourceError, "duplicate player_id"):
            parse_ffc_adp(duplicates, self.query, retrieved_at=self.retrieved_at)

    def test_fetch_preserves_raw_response_and_http_provenance(self) -> None:
        raw = json.dumps(response_payload()).encode("utf-8")
        captured: dict[str, object] = {}

        def fake_urlopen(request: object, *, timeout: float) -> FakeResponse:
            captured["url"] = request.full_url  # type: ignore[attr-defined]
            captured["timeout"] = timeout
            return FakeResponse(raw)

        snapshot = fetch_ffc_adp(
            self.query,
            timeout=7.5,
            retrieved_at=self.retrieved_at,
            urlopen_fn=fake_urlopen,
        )

        self.assertEqual(captured, {"url": self.query.url, "timeout": 7.5})
        self.assertEqual(snapshot.raw_bytes, raw)
        self.assertEqual(snapshot.raw_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(snapshot.response_etag, '"fixture"')

    def test_writes_atomic_immutable_snapshot_with_manifest(self) -> None:
        snapshot = parse_ffc_adp(
            response_payload(),
            self.query,
            retrieved_at=self.retrieved_at,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = write_ffc_snapshot(snapshot, directory)
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            normalized = (path / "adp.csv").read_bytes()
            rows = list(csv.DictReader(io.StringIO(normalized.decode("utf-8"))))

            self.assertEqual(path.name, "20260902T183000.000000Z")
            self.assertEqual(manifest["quality"]["record_count"], 2)
            self.assertEqual(manifest["quality"]["position_counts"], {"DST": 1, "RB": 1})
            self.assertEqual(
                manifest["artifacts"]["normalized"]["sha256"],
                hashlib.sha256(normalized).hexdigest(),
            )
            self.assertEqual(rows[0]["source_player_id"], "1001")
            self.assertEqual(rows[1]["position"], "DST")
            self.assertEqual(rows[0]["retrieved_at"], "2026-09-02T18:30:00Z")
            self.assertFalse(
                any(item.name.startswith(".staging-") for item in path.parent.iterdir())
            )

            with self.assertRaises(FileExistsError):
                write_ffc_snapshot(snapshot, directory)


if __name__ == "__main__":
    unittest.main()
