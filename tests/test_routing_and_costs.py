import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_tmp = tempfile.TemporaryDirectory()
os.environ["HERMES_PROJECTS_DIR"] = _tmp.name  # keep every test write out of the real home folder
sys.path[:0] = [str(ROOT / "router"), str(ROOT / "cost")]

import cost_router  # noqa: E402
import cost_tracker  # noqa: E402
import router  # noqa: E402


class SmartRouterTests(unittest.TestCase):
    def setUp(self):
        self.r = router.SmartRouter()

    def tier(self, text):
        return self.r.classify_task(text)[0]

    def test_simple_commands_go_to_the_free_local_model(self):
        for text in ("curl https://example.com", "ls -la", "cat notes.txt", "check ssl example.com"):
            self.assertEqual(self.tier(text), "FREE", text)

    def test_research_and_audits_go_to_the_cheap_tier(self):
        for text in ("web search for seo trends", "audit example.org", "summarize this report"):
            self.assertEqual(self.tier(text), "CHEAP", text)

    def test_browser_work_is_flagged_expensive(self):
        self.assertEqual(self.tier("take a screenshot of the page"), "EXPENSIVE_WARNING")

    def test_unknown_input_defaults_to_cheap_not_free_or_premium(self):
        self.assertEqual(self.tier("zzzz qqqq"), "CHEAP")

    def test_free_tier_uses_the_local_model_at_zero_cost(self):
        _, rules = self.r.classify_task("ls")
        self.assertIn("--provider local", rules["command"])
        self.assertEqual(rules["cost"], "$0.00")

    def test_writes_stay_inside_the_configured_folder(self):
        self.r.log("test entry")
        self.assertTrue(str(self.r.log_file).startswith(_tmp.name))


class CostRouterTests(unittest.TestCase):
    def test_header_check_is_free_and_local(self):
        rec = cost_router.classify_task("curl -I https://example.com")
        self.assertEqual((rec["tier"], rec["provider"], rec["cost_per_m"]), ("FREE", "local", 0.0))

    def test_web_search_is_cheap(self):
        self.assertEqual(cost_router.classify_task("web_search SEO trends")["tier"], "CHEAP")

    def test_never_routes_to_a_premium_model(self):
        for text in ("web_search SEO trends", "anything else", "curl -I https://example.com"):
            self.assertNotIn("claude", cost_router.classify_task(text)["model"])


class CostTrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = cost_tracker.CostTracker()

    def test_local_models_cost_nothing(self):
        self.assertEqual(self.t.estimate_cost("qwen2.5:14b", 1_000_000, 1_000_000)["total"], 0)

    def test_premium_pricing_per_million_tokens(self):
        self.assertAlmostEqual(self.t.estimate_cost("claude-sonnet", 1_000_000, 1_000_000)["total"], 18.0)

    def test_provider_prefix_and_suffix_are_normalised(self):
        got = self.t.estimate_cost("moonshotai/kimi-k2-thinking", 1_000_000, 1_000_000)
        self.assertAlmostEqual(got["total"], 0.75)

    def test_unknown_model_gets_a_cheap_default_not_zero(self):
        self.assertGreater(self.t.estimate_cost("mystery-model", 1_000_000, 0)["total"], 0)


if __name__ == "__main__":
    unittest.main()
