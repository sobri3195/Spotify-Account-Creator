import json
import tempfile
import unittest

from selenium.webdriver.common.by import By

from spotify_account_creator import (
    POST_CREATION_MODE_ACCOUNT_ONLY,
    SpotifyAccountCreator,
)


class DummyCreator(SpotifyAccountCreator):
    def setup_driver(self):
        self.driver = None


class ConfigValidationTests(unittest.TestCase):
    def test_invalid_ranges_and_mode_are_sanitized(self):
        payload = {
            "delays": {
                "min_typing_delay": 1.0,
                "max_typing_delay": 0.2,
                "min_page_load_delay": -2,
                "max_page_load_delay": 3,
            },
            "retry_attempts": -4,
            "post_creation": {
                "mode": "unknown_mode",
                "max_artists_to_follow": 0,
                "max_playlist_scrolls": 0,
            },
        }

        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fp:
            json.dump(payload, fp)
            path = fp.name

        creator = DummyCreator(config_path=path)

        self.assertLessEqual(
            creator.config['delays']['min_typing_delay'],
            creator.config['delays']['max_typing_delay'],
        )
        self.assertGreaterEqual(creator.config['delays']['min_page_load_delay'], 0)
        self.assertEqual(creator.config['retry_attempts'], 0)
        self.assertEqual(creator.config['post_creation']['mode'], POST_CREATION_MODE_ACCOUNT_ONLY)
        self.assertEqual(creator.config['post_creation']['max_artists_to_follow'], 1)
        self.assertEqual(creator.config['post_creation']['max_playlist_scrolls'], 1)


class DriverRecoveryTests(unittest.TestCase):
    def test_proxy_error_is_detected(self):
        err = Exception("unknown error: net::ERR_PROXY_CONNECTION_FAILED")
        self.assertTrue(SpotifyAccountCreator._is_proxy_connection_error(err))

    def test_invalid_session_error_is_detected(self):
        err = Exception("invalid session id: session deleted as the browser has closed the connection")
        self.assertTrue(SpotifyAccountCreator._is_invalid_session_error(err))


class SignupFieldSelectorTests(unittest.TestCase):
    def test_email_candidates_include_modern_selectors(self):
        candidates = SpotifyAccountCreator._field_candidates('email')
        self.assertIn((By.CSS_SELECTOR, "input[type='email']"), candidates)
        self.assertIn((By.CSS_SELECTOR, "input[autocomplete='email']"), candidates)

    def test_unknown_field_candidates_empty(self):
        self.assertEqual(SpotifyAccountCreator._field_candidates('does_not_exist'), [])


if __name__ == '__main__':
    unittest.main()
