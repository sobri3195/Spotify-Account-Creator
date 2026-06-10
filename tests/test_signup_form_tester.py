import json
import tempfile
import unittest
from pathlib import Path

from signup_form_tester import DEFAULT_SIGNUP_URL, By, InvalidSessionIdException, SignupFormTester


class DummyTester(SignupFormTester):
    def setup_driver(self):
        self.driver = None


class ConfigValidationTests(unittest.TestCase):
    def make_tester(self, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fp:
            json.dump(payload, fp)
            path = fp.name
        return DummyTester(config_path=path, auto_setup_driver=False)

    def test_invalid_ranges_and_retry_attempts_are_sanitized(self):
        tester = self.make_tester(
            {
                "delays": {
                    "min_typing_delay": 1.0,
                    "max_typing_delay": 0.2,
                    "min_page_load_delay": -2,
                    "max_page_load_delay": 3,
                },
                "retry_attempts": -4,
            }
        )

        self.assertLessEqual(
            tester.config["delays"]["min_typing_delay"],
            tester.config["delays"]["max_typing_delay"],
        )
        self.assertGreaterEqual(tester.config["delays"]["min_page_load_delay"], 0)
        self.assertEqual(tester.config["retry_attempts"], 0)

    def test_non_local_signup_url_is_replaced_with_default(self):
        tester = self.make_tester({"signup_url": "https://example.com/signup"})
        self.assertEqual(tester.config["signup_url"], DEFAULT_SIGNUP_URL)

    def test_file_fixture_url_is_allowed_for_local_tests(self):
        fixture_url = Path("tests/fixtures/signup.html").resolve().as_uri()
        tester = self.make_tester({"signup_url": fixture_url})
        self.assertEqual(tester.config["signup_url"], fixture_url)

    def test_retry_attempts_are_bounded(self):
        self.assertEqual(SignupFormTester.sanitize_retry_attempts(999), 10)
        self.assertEqual(SignupFormTester.sanitize_retry_attempts("bad"), 2)

    def test_unsafe_proxy_and_evasion_config_keys_are_removed(self):
        tester = self.make_tester(
            {
                "proxy_rotation": {"enabled": True},
                "browser": {
                    "headless": True,
                    "anti_detection": True,
                    "fingerprint_profile": "spoofed",
                },
                "nested": [
                    {"captcha_solver": "service"},
                    {"safe_note": "kept"},
                ],
            }
        )

        self.assertNotIn("proxy_rotation", tester.config)
        self.assertNotIn("anti_detection", tester.config["browser"])
        self.assertNotIn("fingerprint_profile", tester.config["browser"])
        self.assertNotIn("captcha_solver", tester.config["nested"][0])
        self.assertEqual(tester.config["nested"][1]["safe_note"], "kept")

    def test_strip_disallowed_config_keys_reports_dotted_paths(self):
        cleaned, removed = SignupFormTester.strip_disallowed_config_keys(
            {"safe": {"proxy_url": "http://localhost:9000"}, "items": [{"captcha": True}]}
        )

        self.assertEqual(cleaned, {"safe": {}, "items": [{}]})
        self.assertEqual(removed, ["safe.proxy_url", "items.0.captcha"])


class DriverRecoveryTests(unittest.TestCase):
    def test_invalid_session_error_is_detected_from_exception_type(self):
        self.assertTrue(SignupFormTester.is_invalid_session_error(InvalidSessionIdException()))

    def test_invalid_session_error_is_detected_from_message(self):
        err = Exception("invalid session id: browser closed")
        self.assertTrue(SignupFormTester.is_invalid_session_error(err))

    def test_proxy_error_helper_has_been_removed(self):
        self.assertFalse(hasattr(SignupFormTester, "_is_proxy_connection_error"))


class SignupFieldSelectorTests(unittest.TestCase):
    def test_email_candidates_include_safe_generic_selectors(self):
        candidates = SignupFormTester.field_candidates("email")
        self.assertIn((By.CSS_SELECTOR, "input[type='email']"), candidates)
        self.assertIn((By.CSS_SELECTOR, "input[autocomplete='email']"), candidates)

    def test_local_mock_field_candidates_include_fixture_ids(self):
        self.assertIn((By.ID, "email"), SignupFormTester.field_candidates("email"))
        self.assertIn((By.ID, "password"), SignupFormTester.field_candidates("password"))
        self.assertIn((By.ID, "displayName"), SignupFormTester.field_candidates("display_name"))
        self.assertIn((By.ID, "month"), SignupFormTester.field_candidates("month"))

    def test_unknown_field_candidates_empty(self):
        self.assertEqual(SignupFormTester.field_candidates("does_not_exist"), [])

    def test_submit_candidates_target_local_form_controls(self):
        candidates = SignupFormTester.field_candidates("submit")
        self.assertIn((By.CSS_SELECTOR, "button[type='submit']"), candidates)
        self.assertIn((By.CSS_SELECTOR, "button[data-testid='signup-submit']"), candidates)


class LocalMockBehaviorTests(unittest.TestCase):
    def test_fixture_contains_success_indicator_and_no_third_party_action_copy(self):
        fixture = Path("tests/fixtures/signup.html").read_text(encoding="utf-8")
        self.assertIn("success-message", fixture)
        self.assertNotIn("playlist", fixture.lower())
        self.assertNotIn("captcha", fixture.lower())


if __name__ == "__main__":
    unittest.main()
