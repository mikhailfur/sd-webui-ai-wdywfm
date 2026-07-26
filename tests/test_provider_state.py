import unittest
from pathlib import Path

from ai_wdywfm.infrastructure.provider_state import load_provider_state, save_provider_state


@unittest.skipUnless(__import__("os").name == "nt", "DPAPI is Windows-only")
class ProviderStateTests(unittest.TestCase):
    def test_round_trip_encrypts_openrouter_key(self):
        path = Path(__file__).parent / ".provider-state-test.json"
        try:
            save_provider_state(
                "OpenRouter",
                "openai/test",
                "https://openrouter.ai/api/v1",
                "sk-secret-test",
                path,
            )
            self.assertNotIn("sk-secret-test", path.read_text(encoding="utf-8"))
            state = load_provider_state(path)
            self.assertEqual(state["selected_provider"], "OpenRouter")
            self.assertEqual(state["providers"]["OpenRouter"]["model"], "openai/test")
            self.assertEqual(state["providers"]["OpenRouter"]["api_key"], "sk-secret-test")
        finally:
            path.unlink(missing_ok=True)

    def test_empty_event_preserves_key_and_repairs_openrouter_url(self):
        path = Path(__file__).parent / ".provider-state-test.json"
        try:
            save_provider_state(
                "OpenRouter", "google/gemma-4-31b-it",
                "https://openrouter.ai/api/v1", "sk-secret-test", path,
            )
            save_provider_state(
                "OpenRouter", "google/gemma-4-31b-it",
                "http://127.0.0.1:1234/v1", "", path,
            )
            state = load_provider_state(path)
            self.assertEqual(
                state["providers"]["OpenRouter"]["base_url"],
                "https://openrouter.ai/api/v1",
            )
            self.assertEqual(
                state["providers"]["OpenRouter"]["api_key"], "sk-secret-test"
            )
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
