import unittest

from ai_wdywfm.infrastructure.diagnostics import redact


class DiagnosticsTests(unittest.TestCase):
    def test_redacts_openrouter_and_bearer_secrets(self):
        text = "api_key=sk-or-v1-abcdef Authorization: Bearer another-secret"
        result = redact(text)
        self.assertNotIn("abcdef", result)
        self.assertNotIn("another-secret", result)
        self.assertGreaterEqual(result.count("[REDACTED]"), 2)


if __name__ == "__main__":
    unittest.main()
