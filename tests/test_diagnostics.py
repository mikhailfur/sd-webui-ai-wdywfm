import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from ai_wdywfm.infrastructure.diagnostics import read_log_tail, redact


class DiagnosticsTests(unittest.TestCase):
    def test_redacts_openrouter_and_bearer_secrets(self):
        text = "api_key=sk-or-v1-abcdef Authorization: Bearer another-secret"
        result = redact(text)
        self.assertNotIn("abcdef", result)
        self.assertNotIn("another-secret", result)
        self.assertGreaterEqual(result.count("[REDACTED]"), 2)

    def test_jsonl_tail_supports_request_and_level_filters(self):
        rows = [
            {"level": "INFO", "request": "one", "message": "first"},
            {"level": "WARNING", "request": "two", "message": "second"},
            {"level": "WARNING", "request": "one", "message": "third"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "diagnostics.jsonl"
            path.write_text(
                "\n".join(json.dumps(row) for row in rows),
                encoding="utf-8",
            )
            with patch(
                "ai_wdywfm.infrastructure.diagnostics.log_path",
                return_value=path,
            ):
                value = read_log_tail(
                    request_filter="one", level_filter="WARNING",
                )
        self.assertIn("third", value)
        self.assertNotIn("first", value)
        self.assertNotIn("second", value)


if __name__ == "__main__":
    unittest.main()
