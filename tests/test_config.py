"""Tests for configuration parsing helpers."""

from __future__ import annotations

import unittest
from datetime import timezone

from tg_media_dl.config import parse_datetime_filter, parse_proxy


class ConfigTests(unittest.TestCase):
    """Configuration helper tests."""

    def test_parse_datetime_filter_returns_utc_datetime(self) -> None:
        """Date-only filters should become timezone-aware UTC datetimes."""
        value = parse_datetime_filter("2026-07-04", "--since")

        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value.tzinfo, timezone.utc)

    def test_parse_until_date_uses_end_of_day(self) -> None:
        """Date-only until filters should include the whole local day."""
        value = parse_datetime_filter("2026-07-04", "--until", end_of_day=True)

        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value.tzinfo, timezone.utc)
        self.assertEqual(value.astimezone().date().isoformat(), "2026-07-04")

    def test_parse_proxy_rejects_non_socks5(self) -> None:
        """Only SOCKS5 proxies are accepted."""
        with self.assertRaises(SystemExit):
            parse_proxy("http://localhost:8080")


if __name__ == "__main__":
    unittest.main()
