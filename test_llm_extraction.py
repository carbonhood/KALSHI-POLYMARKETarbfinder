# Unit tests for LLM extraction cache layer (no API calls).
import json
import tempfile
import unittest
from pathlib import Path

import llm_extraction_cache as cache_mod
import config
from canonical_derive import derive_from_extraction
from extraction_validator import validate_extraction
from llm_extraction_cache import get_cached_record, save_cached_record
from llm_market_payload import cache_key_for_market, content_hash_for_market
from outcome_normalization import attach_event_metadata


class LLMExtractionTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_path = Path(self._tmpdir.name) / "test_cache.sqlite"
        self._orig_cache_path = config.LLM_CACHE_PATH
        config.LLM_CACHE_PATH = str(self._cache_path)
        cache_mod.close_cache()

    def tearDown(self):
        cache_mod.close_cache()
        config.LLM_CACHE_PATH = self._orig_cache_path
        self._tmpdir.cleanup()

    def test_cache_round_trip(self):
        market = {
            "platform": "Polymarket",
            "condition_id": "0xabc",
            "market_question": "Will Example Event happen?",
            "event_title": "Example Event",
        }
        extraction = {
            "event_type": "geopolitical",
            "event_id": "example_event_2026",
            "entities": {"topic": "example"},
            "outcome": {"label": "yes", "kind": "binary"},
            "confidence": 0.91,
            "resolution_risk_flags": [],
        }
        save_cached_record(market, extraction, valid=True, model="test")

        cached = get_cached_record(market)
        self.assertIsNotNone(cached)
        self.assertTrue(cached["valid"])
        self.assertEqual(cached["extraction"]["event_id"], "example_event_2026")

    def test_content_hash_invalidation(self):
        market = {
            "platform": "Kalshi",
            "ticker": "TICK-1",
            "market_question": "Original question?",
        }
        extraction = {
            "event_type": "other",
            "event_id": "original",
            "outcome": {"label": "yes"},
            "confidence": 0.9,
            "resolution_risk_flags": [],
        }
        save_cached_record(market, extraction, valid=True)

        market["market_question"] = "Changed question?"
        self.assertIsNone(get_cached_record(market))

    def test_attach_uses_cache_when_regex_misses(self):
        market = {
            "platform": "Kalshi",
            "ticker": "GEO-1",
            "market_question": "Will leaders meet before 2027?",
        }
        extraction = {
            "event_type": "geopolitical",
            "event_id": "leader_meeting_2026",
            "entities": {"year": 2026},
            "outcome": {"label": "yes", "kind": "binary"},
            "confidence": 0.92,
            "resolution_risk_flags": [],
        }
        save_cached_record(market, extraction, valid=True)

        attach_event_metadata(market)
        self.assertEqual(market["metadata_source"], "llm_cache")
        self.assertEqual(market["event_key"][0], "geopolitical")

    def test_regex_wins_over_cache(self):
        market = {
            "platform": "Kalshi",
            "ticker": "KXFEDDEC-26JUL-H0",
            "market_question": "Will the Fed maintain the target rate at the July 2026 meeting?",
            "yes_sub_title": "Maintain current rate",
            "event_title": "Fed decision July 2026",
            "end_date": "2026-07-30T00:00:00Z",
        }
        extraction = {
            "event_type": "geopolitical",
            "event_id": "wrong_type",
            "outcome": {"label": "hold"},
            "confidence": 0.99,
            "resolution_risk_flags": [],
        }
        save_cached_record(market, extraction, valid=True)

        attach_event_metadata(market)
        self.assertEqual(market["metadata_source"], "regex")
        self.assertEqual(market["event_key"][0], "central_bank")

    def test_validator_rejects_low_confidence(self):
        extraction = {
            "event_type": "geopolitical",
            "event_id": "test_event",
            "outcome": {"label": "yes"},
            "confidence": 0.5,
            "resolution_risk_flags": [],
        }
        ok, errors = validate_extraction(extraction)
        self.assertFalse(ok)
        self.assertTrue(any("confidence" in err for err in errors))

    def test_derive_central_bank(self):
        extraction = {
            "event_type": "central_bank",
            "event_id": "federal_reserve_2026_07",
            "entities": {"institution": "federal_reserve", "year": 2026, "month": 7},
            "outcome": {"label": "hold"},
            "confidence": 0.95,
            "resolution_risk_flags": [],
        }
        derived = derive_from_extraction(extraction)
        self.assertEqual(
            derived["event_key"],
            ("central_bank", "federal_reserve", 2026, 7),
        )


if __name__ == "__main__":
    unittest.main()
