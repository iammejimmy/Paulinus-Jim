import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ytagent import scoring
from ytagent.store import Store
from ytagent.uploader import next_slots


def video(views, age_days, subs):
    return {"views": views, "age_days": age_days, "channel_subs": subs}


NICHE = {"rpm_low_usd": 4, "rpm_high_usd": 8, "faceless_friendly": True, "evergreen": 8}


class ScoringTests(unittest.TestCase):
    def test_keyword_metrics(self):
        m = scoring.keyword_metrics([
            video(100_000, 10, 5_000),       # small channel breakout
            video(2_000_000, 20, 3_000_000),  # big channel
            video(50_000, 50, 200_000),
        ])
        self.assertEqual(m["videos"], 3)
        self.assertEqual(m["median_views"], 100_000)
        self.assertAlmostEqual(m["small_channel_share"], 1 / 3, places=3)
        self.assertAlmostEqual(m["big_channel_share"], 1 / 3, places=3)
        self.assertEqual(m["small_channel_median_views"], 100_000)

    def test_empty_keyword(self):
        self.assertEqual(scoring.keyword_metrics([])["videos"], 0)
        self.assertEqual(scoring.combine_metrics([scoring.keyword_metrics([])])["videos"], 0)

    def test_open_niche_beats_saturated_one(self):
        open_niche = scoring.keyword_metrics([video(80_000, 30, 8_000) for _ in range(10)])
        saturated = scoring.keyword_metrics([video(80_000, 30, 5_000_000) for _ in range(10)])
        a = scoring.opportunity_score(open_niche, NICHE)
        b = scoring.opportunity_score(saturated, NICHE)
        self.assertGreater(a["score"], b["score"])
        self.assertTrue(0 <= b["score"] <= a["score"] <= 100)

    def test_higher_rpm_scores_higher(self):
        m = scoring.keyword_metrics([video(80_000, 30, 20_000) for _ in range(5)])
        low = scoring.opportunity_score(m, {**NICHE, "rpm_low_usd": 1, "rpm_high_usd": 2})
        high = scoring.opportunity_score(m, {**NICHE, "rpm_low_usd": 12, "rpm_high_usd": 20})
        self.assertGreater(high["score"], low["score"])
        self.assertGreater(high["est_monthly_revenue_usd"], low["est_monthly_revenue_usd"])


class ScheduleTests(unittest.TestCase):
    NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)  # a Monday

    def test_slots_follow_schedule(self):
        slots = next_slots(3, ["mon", "wed", "fri"], ["15:00"], "America/New_York", [], now=self.NOW)
        # 15:00 New York (EDT) = 19:00 UTC
        self.assertEqual([s.isoformat() for s in slots], [
            "2026-09-21T19:00:00+00:00", "2026-09-23T19:00:00+00:00", "2026-09-25T19:00:00+00:00",
        ])

    def test_slots_queue_after_taken(self):
        taken = ["2026-09-23T19:00:00+00:00"]
        slots = next_slots(1, ["mon", "wed", "fri"], ["15:00"], "America/New_York", taken, now=self.NOW)
        self.assertEqual(slots[0].isoformat(), "2026-09-25T19:00:00+00:00")

    def test_min_lead_time(self):
        late = datetime(2026, 9, 21, 18, 30, tzinfo=timezone.utc)
        slots = next_slots(1, ["mon", "wed"], ["15:00"], "America/New_York", [], now=late)
        self.assertEqual(slots[0].isoformat(), "2026-09-23T19:00:00+00:00")


class StoreTests(unittest.TestCase):
    def test_video_lifecycle(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "state.db")
            s.save_niche("Ancient history", 71.5, {"name": "Ancient history", "score": 71.5})
            s.save_niche("Crypto", 40.0, {"name": "Crypto", "score": 40.0})
            self.assertEqual(s.top_niches(1)[0]["name"], "Ancient history")
            self.assertEqual(s.get_niche("ancient HISTORY")["score"], 71.5)

            vid = s.add_video("Ancient history", {"title": "T1"}, "v.mp4", "t.jpg", "rendered")
            self.assertEqual([v["id"] for v in s.videos("rendered")], [vid])
            s.update_video(vid, status="scheduled", youtube_id="abc", publish_at="2026-09-23T19:00:00+00:00")
            self.assertEqual(s.videos("scheduled")[0]["youtube_id"], "abc")
            self.assertEqual(s.scheduled_times(), ["2026-09-23T19:00:00+00:00"])
            self.assertEqual(s.titles("Ancient history"), ["T1"])


if __name__ == "__main__":
    unittest.main()
