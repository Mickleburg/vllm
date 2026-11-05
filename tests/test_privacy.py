import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from privacy_logging import MetadataFormatter


class PrivacyTest(unittest.TestCase):
    def test_messages_and_exceptions_are_never_formatted(self):
        record = logging.LogRecord("vllm", logging.ERROR, "x.py", 10,
                                   "prompt %s", ("SECRET_PROMPT",),
                                   (ValueError, ValueError("SECRET_RESPONSE"), None))
        output = MetadataFormatter().format(record)
        self.assertNotIn("SECRET", output)
        self.assertIn('"level": "ERROR"', output)

    def test_access_drops_query_and_unknown_paths(self):
        for path, route in [("/v1/chat/completions?secret=SECRET", "/v1/chat/completions"),
                            ("/SECRET", "other")]:
            record = logging.LogRecord("uvicorn.access", logging.INFO, "x.py", 1,
                                       "%s %s %s %s %s", ("SECRET", "POST", path, "1.1", 200), None)
            output = MetadataFormatter().format(record)
            self.assertNotIn("SECRET", output)
            self.assertIn(route, output)


if __name__ == "__main__":
    unittest.main()
