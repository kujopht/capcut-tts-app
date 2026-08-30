import unittest
from datetime import datetime, timedelta, timezone

from server.chat.privacy import (
    DEFAULT_RETENTION_POLICY, RetentionPolicy, is_expired, redact_for_logging,
)


class IsExpiredTest(unittest.TestCase):
    def test_recent_conversation_not_expired(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        last_updated = now - timedelta(days=1)
        self.assertFalse(is_expired(last_updated, now=now))

    def test_old_conversation_expired(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        last_updated = now - timedelta(days=31)
        self.assertTrue(is_expired(last_updated, now=now))

    def test_exact_boundary_not_yet_expired(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        policy = RetentionPolicy(conversation_retention_days=30)
        last_updated = now - timedelta(days=30)
        self.assertFalse(is_expired(last_updated, policy=policy, now=now))

    def test_custom_policy_shorter_window(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        policy = RetentionPolicy(conversation_retention_days=1)
        last_updated = now - timedelta(days=2)
        self.assertTrue(is_expired(last_updated, policy=policy, now=now))

    def test_default_policy_is_thirty_days(self):
        self.assertEqual(DEFAULT_RETENTION_POLICY.conversation_retention_days, 30)


class RedactForLoggingTest(unittest.TestCase):
    def test_short_text_unaffected(self):
        self.assertEqual(redact_for_logging("hello"), "hello")

    def test_long_text_truncated(self):
        result = redact_for_logging("x" * 500, max_len=50)
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(len(result), 51)

    def test_control_characters_stripped(self):
        result = redact_for_logging("hello\x00\x1bworld")
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x1b", result)

    def test_empty_string(self):
        self.assertEqual(redact_for_logging(""), "")


if __name__ == "__main__":
    unittest.main()
