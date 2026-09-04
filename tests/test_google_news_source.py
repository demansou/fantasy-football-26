import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone

from fantasy_draft.sources.google_news import (
    GoogleNewsQuery,
    build_search_query,
    parse_google_news_rss,
    write_google_news_snapshot,
    GoogleNewsSnapshot,
)


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Seahawks play caller explains motion and offensive scheme</title>
    <link>https://news.google.com/rss/articles/one</link>
    <guid>one</guid>
    <pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate>
    <source url="https://example.com">Example News</source>
  </item>
  <item>
    <title>Seattle offensive line starter returns from injury</title>
    <link>https://news.google.com/rss/articles/two</link>
    <guid>two</guid>
    <pubDate>Mon, 31 Aug 2026 12:00:00 GMT</pubDate>
    <source url="https://second.example">Second Source</source>
  </item>
  <item>
    <title>Duplicate</title><link>https://news.google.com/rss/articles/two</link>
    <guid>two</guid><pubDate>Mon, 31 Aug 2026 12:00:00 GMT</pubDate>
    <source url="https://second.example">Second Source</source>
  </item>
</channel></rss>"""


class GoogleNewsSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retrieved_at = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)

    def test_query_and_search_text_are_explicit(self) -> None:
        query = GoogleNewsQuery(2026, teams=("SEA",), lookback_days=30, max_articles_per_team=10)
        self.assertEqual(query.teams, ("SEA",))
        text = build_search_query("SEA", "Brian Fleury", 30)
        self.assertIn('"Seattle Seahawks"', text)
        self.assertIn('"Brian Fleury"', text)
        self.assertIn("when:30d", text)
        with self.assertRaisesRegex(ValueError, "between 1 and 365"):
            GoogleNewsQuery(2026, teams=("SEA",), lookback_days=0)

    def test_parses_metadata_and_topic_hints_without_sentiment(self) -> None:
        articles = parse_google_news_rss(
            RSS,
            season=2026,
            team="SEA",
            query="query",
            play_caller="Brian Fleury",
            retrieved_at=self.retrieved_at,
            max_articles=10,
        )
        self.assertEqual(len(articles), 2)
        self.assertIn("play_calling", articles[0].topic_hints)
        self.assertIn("scheme_style", articles[0].topic_hints)
        self.assertIn("offensive_line", articles[1].topic_hints)
        self.assertIn("injury_availability", articles[1].topic_hints)
        self.assertEqual(articles[0].to_row()["sentiment_used"], "false")

    def test_writes_raw_xml_and_hashed_discovery_table(self) -> None:
        query = GoogleNewsQuery(2026, teams=("SEA",), lookback_days=30, max_articles_per_team=10)
        search = build_search_query("SEA", "Brian Fleury", 30)
        articles = parse_google_news_rss(
            RSS,
            season=2026,
            team="SEA",
            query=search,
            play_caller="Brian Fleury",
            retrieved_at=self.retrieved_at,
            max_articles=10,
        )
        snapshot = GoogleNewsSnapshot(
            query=query,
            retrieved_at=self.retrieved_at,
            callers={"SEA": "Brian Fleury"},
            search_queries={"SEA": search},
            raw_xml={"SEA": RSS},
            articles=articles,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_google_news_snapshot(snapshot, directory)
            manifest = json.loads((path / "manifest.json").read_text())
            article_bytes = (path / "articles.csv").read_bytes()
            with (path / "articles.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertFalse(any(row["sentiment_used"] == "true" for row in rows))
            self.assertEqual(manifest["artifacts"]["articles.csv"]["sha256"], hashlib.sha256(article_bytes).hexdigest())
            self.assertTrue((path / "raw" / "SEA.xml").is_file())


if __name__ == "__main__":
    unittest.main()
