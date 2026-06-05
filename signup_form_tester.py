"""Safe Selenium QA automation for local/mock signup forms.

This module is intentionally limited to testing signup forms that you own or are
explicitly authorized to test. It does not include proxying, CAPTCHA bypass,
anti-detection behavior, fake third-party account generation, or any post-signup
engagement automation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        ElementClickInterceptedException,
        InvalidSessionIdException,
        StaleElementReferenceException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal CI images.
    webdriver = None  # type: ignore[assignment]
    ChromeDriverManager = None  # type: ignore[assignment]

    class WebDriverException(Exception):
        """Fallback used so config/unit tests can run without Selenium installed."""

    class ElementClickInterceptedException(WebDriverException):
        pass

    class InvalidSessionIdException(WebDriverException):
        pass

    class StaleElementReferenceException(WebDriverException):
        pass

    class TimeoutException(WebDriverException):
        pass

    class Service:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("Selenium is required to start a browser session.")

    class By:  # type: ignore[no-redef]
        ID = "id"
        NAME = "name"
        CSS_SELECTOR = "css selector"
        XPATH = "xpath"
        CLASS_NAME = "class name"

    class Keys:  # type: ignore[no-redef]
        CONTROL = "\ue009"
        DELETE = "\ue003"

    class WebDriver:  # type: ignore[no-redef]
        pass

    class WebElement:  # type: ignore[no-redef]
        pass

    class Select:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("Selenium is required to interact with select elements.")

    class WebDriverWait:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("Selenium is required to wait for browser elements.")

    class _ExpectedConditions:
        @staticmethod
        def element_to_be_clickable(locator: Locator) -> Locator:
            return locator

        @staticmethod
        def presence_of_element_located(locator: Locator) -> Locator:
            return locator

    EC = _ExpectedConditions()  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

DEFAULT_SIGNUP_URL = "http://localhost:8000/signup"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
Locator = Tuple[str, str]

DEFAULT_CONFIG: Dict[str, Any] = {
    "signup_url": DEFAULT_SIGNUP_URL,
    "browser": {
        "headless": False,
        "window_size": "1280,900",
        "page_load_timeout": 20,
    },
    "delays": {
        "min_typing_delay": 0.0,
        "max_typing_delay": 0.05,
        "min_page_load_delay": 0.1,
        "max_page_load_delay": 0.3,
        "min_attempt_delay": 0.1,
        "max_attempt_delay": 0.3,
        "min_action_delay": 0.0,
        "max_action_delay": 0.1,
    },
    "retry_attempts": 2,
    "success_indicators": [
        "success-message",
        "signup-success",
        "account-created",
    ],
    "test_user": {
        "email": "qa@example.test",
        "password": "CorrectHorseBatteryStaple!23",
        "display_name": "QA Tester",
        "day": "12",
        "month": "5",
        "year": "1995",
    },
}


@dataclass(frozen=True)
class SignupResult:
    """Outcome of a local signup form test run."""

    submitted: bool
    success: bool
    url: str


class ConfigError(ValueError):
    """Raised when safe configuration validation cannot continue."""


class SignupFormTester:
    """Selenium helper for authorized QA of local/mock signup forms."""

    def __init__(
        self,
        config_path: str = "config.json",
        *,
        driver: Optional[WebDriver] = None,
        auto_setup_driver: bool = True,
    ) -> None:
        self.config_path = config_path
        self.config = self.load_config(config_path)
        self.validate_config()
        self.driver: Optional[WebDriver] = driver

        if self.driver is None and auto_setup_driver:
            self.setup_driver()

    @staticmethod
    def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
        merged = deepcopy(dict(base))
        for key, value in override.items():
            if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
                merged[key] = SignupFormTester._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    @classmethod
    def load_config(cls, config_path: str) -> Dict[str, Any]:
        """Load JSON configuration and merge it with safe defaults."""
        if not os.path.exists(config_path):
            return deepcopy(DEFAULT_CONFIG)

        try:
            with open(config_path, "r", encoding="utf-8") as config_file:
                user_config = json.load(config_file)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not load %s: %s. Using default config.", config_path, exc)
            return deepcopy(DEFAULT_CONFIG)

        if not isinstance(user_config, Mapping):
            LOGGER.warning("Config root must be an object. Using default config.")
            return deepcopy(DEFAULT_CONFIG)

        return cls._deep_merge(DEFAULT_CONFIG, user_config)

    @staticmethod
    def _is_local_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            return True
        if parsed.scheme not in {"http", "https"}:
            return False
        return (parsed.hostname or "").lower() in LOCAL_HOSTS

    @staticmethod
    def sanitize_delay_range(delays: Dict[str, Any], min_key: str, max_key: str) -> None:
        """Clamp a delay range to non-negative numbers and fix reversed ranges."""
        try:
            min_value = float(delays.get(min_key, DEFAULT_CONFIG["delays"].get(min_key, 0.0)))
        except (TypeError, ValueError):
            min_value = float(DEFAULT_CONFIG["delays"].get(min_key, 0.0))
        try:
            max_value = float(delays.get(max_key, DEFAULT_CONFIG["delays"].get(max_key, 0.0)))
        except (TypeError, ValueError):
            max_value = float(DEFAULT_CONFIG["delays"].get(max_key, 0.0))

        min_value = max(0.0, min_value)
        max_value = max(0.0, max_value)
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        delays[min_key] = min_value
        delays[max_key] = max_value

    @staticmethod
    def sanitize_retry_attempts(value: Any) -> int:
        """Return a bounded, non-negative retry attempt count."""
        try:
            attempts = int(value)
        except (TypeError, ValueError):
            attempts = int(DEFAULT_CONFIG["retry_attempts"])
        return min(max(attempts, 0), 10)

    def validate_config(self) -> None:
        """Validate and self-heal config values while enforcing local-only targets."""
        url = str(self.config.get("signup_url") or DEFAULT_SIGNUP_URL)
        if not self._is_local_url(url):
            LOGGER.warning("Non-local signup_url %r is not allowed. Using %s.", url, DEFAULT_SIGNUP_URL)
            url = DEFAULT_SIGNUP_URL
        self.config["signup_url"] = url

        delays = self.config.setdefault("delays", {})
        for min_key, max_key in (
            ("min_typing_delay", "max_typing_delay"),
            ("min_page_load_delay", "max_page_load_delay"),
            ("min_attempt_delay", "max_attempt_delay"),
            ("min_action_delay", "max_action_delay"),
        ):
            self.sanitize_delay_range(delays, min_key, max_key)

        self.config["retry_attempts"] = self.sanitize_retry_attempts(self.config.get("retry_attempts"))

        browser = self.config.setdefault("browser", {})
        browser["headless"] = bool(browser.get("headless", False))
        browser["window_size"] = str(browser.get("window_size") or DEFAULT_CONFIG["browser"]["window_size"])
        try:
            browser["page_load_timeout"] = max(1, int(browser.get("page_load_timeout", 20)))
        except (TypeError, ValueError):
            browser["page_load_timeout"] = DEFAULT_CONFIG["browser"]["page_load_timeout"]

        indicators = self.config.get("success_indicators")
        if not isinstance(indicators, list) or not all(isinstance(item, str) for item in indicators):
            self.config["success_indicators"] = deepcopy(DEFAULT_CONFIG["success_indicators"])

    def setup_driver(self) -> None:
        """Create a standard Chrome WebDriver session without evasion settings."""
        if webdriver is None or ChromeDriverManager is None:
            raise RuntimeError("Install selenium and webdriver-manager to start browser sessions.")

        browser = self.config["browser"]
        options = webdriver.ChromeOptions()
        options.add_argument(f"--window-size={browser['window_size']}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if browser.get("headless"):
            options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )
        self.driver.set_page_load_timeout(browser["page_load_timeout"])

    def _require_driver(self) -> WebDriver:
        if self.driver is None:
            raise RuntimeError("WebDriver has not been initialized.")
        return self.driver

    @staticmethod
    def is_invalid_session_error(error: Exception) -> bool:
        if isinstance(error, InvalidSessionIdException):
            return True
        message = str(error).lower()
        return "invalid session id" in message or "not connected to devtools" in message

    def refresh_driver_session(self, reason: str = "") -> None:
        """Restart the WebDriver session after a recoverable local test failure."""
        if reason:
            LOGGER.info("Refreshing browser session: %s", reason)
        if self.driver is not None:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
        self.driver = None
        self.setup_driver()

    def _sleep_random(self, min_key: str, max_key: str) -> None:
        delays = self.config["delays"]
        time.sleep(random.uniform(delays[min_key], delays[max_key]))

    def sleep_page_load(self) -> None:
        self._sleep_random("min_page_load_delay", "max_page_load_delay")

    def sleep_action(self) -> None:
        self._sleep_random("min_action_delay", "max_action_delay")

    def sleep_typing(self) -> None:
        self._sleep_random("min_typing_delay", "max_typing_delay")

    @staticmethod
    def field_candidates(field_name: str) -> List[Locator]:
        """Return resilient selector candidates for common signup form fields."""
        candidates: Dict[str, List[Locator]] = {
            "email": [
                (By.ID, "email"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[autocomplete='email']"),
                (By.CSS_SELECTOR, "input[data-testid='email-input']"),
            ],
            "password": [
                (By.ID, "password"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.CSS_SELECTOR, "input[autocomplete='new-password']"),
                (By.CSS_SELECTOR, "input[data-testid='password-input']"),
            ],
            "display_name": [
                (By.ID, "display_name"),
                (By.ID, "displayName"),
                (By.NAME, "display_name"),
                (By.NAME, "displayName"),
                (By.CSS_SELECTOR, "input[autocomplete='name']"),
                (By.CSS_SELECTOR, "input[autocomplete='nickname']"),
                (By.CSS_SELECTOR, "input[aria-label*='name' i]"),
                (By.CSS_SELECTOR, "input[data-testid='display-name-input']"),
            ],
            "day": [
                (By.ID, "day"),
                (By.NAME, "day"),
                (By.CSS_SELECTOR, "input[aria-label*='day' i]"),
                (By.CSS_SELECTOR, "input[data-testid='day-input']"),
            ],
            "month": [
                (By.ID, "month"),
                (By.NAME, "month"),
                (By.CSS_SELECTOR, "select[aria-label*='month' i]"),
                (By.CSS_SELECTOR, "select[data-testid='month-select']"),
                (By.CSS_SELECTOR, "input[aria-label*='month' i]"),
            ],
            "year": [
                (By.ID, "year"),
                (By.NAME, "year"),
                (By.CSS_SELECTOR, "input[aria-label*='year' i]"),
                (By.CSS_SELECTOR, "input[data-testid='year-input']"),
            ],
            "submit": [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.CSS_SELECTOR, "button[data-testid='signup-submit']"),
                (By.XPATH, "//button[contains(., 'Sign up') or contains(., 'Submit') or contains(., 'Create')]"),
            ],
        }
        return candidates.get(field_name, [])

    def find_first(
        self,
        candidates: Sequence[Locator],
        *,
        timeout: float = 5,
        clickable: bool = False,
    ) -> Optional[WebElement]:
        driver = self._require_driver()
        condition = EC.element_to_be_clickable if clickable else EC.presence_of_element_located
        for locator in candidates:
            try:
                return WebDriverWait(driver, timeout).until(condition(locator))
            except (TimeoutException, StaleElementReferenceException):
                continue
        return None

    def safe_click(self, element: WebElement) -> bool:
        """Click an element, falling back to JavaScript for intercepted local UI clicks."""
        driver = self._require_driver()
        try:
            element.click()
            return True
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", element)
            return True
        except WebDriverException as exc:
            LOGGER.warning("Could not click element: %s", exc)
            return False

    @staticmethod
    def safe_clear(element: WebElement) -> bool:
        """Clear an input defensively before test data entry."""
        try:
            element.clear()
            existing = element.get_attribute("value") or ""
            if existing:
                element.send_keys(Keys.CONTROL, "a")
                element.send_keys(Keys.DELETE)
            return True
        except WebDriverException as exc:
            LOGGER.warning("Could not clear element: %s", exc)
            return False

    def fill_field(self, field_name: str, value: str, *, timeout: float = 5) -> bool:
        """Find a field by candidate selectors and fill it with provided QA data."""
        element = self.find_first(self.field_candidates(field_name), timeout=timeout)
        if element is None:
            return False

        tag_name = (element.tag_name or "").lower()
        if tag_name == "select":
            for select_action in (
                lambda: Select(element).select_by_value(str(value)),
                lambda: Select(element).select_by_visible_text(str(value)),
            ):
                try:
                    select_action()
                    return True
                except WebDriverException:
                    continue
            return False

        if not self.safe_clear(element):
            return False
        for character in str(value):
            element.send_keys(character)
            self.sleep_typing()
        return True

    def fill_signup_form(self, user_data: Mapping[str, str]) -> bool:
        """Fill all supported local signup form fields that are present."""
        required_fields = ("email", "password", "display_name")
        filled_required = [self.fill_field(field, str(user_data[field])) for field in required_fields]

        for optional_field in ("day", "month", "year"):
            if optional_field in user_data:
                self.fill_field(optional_field, str(user_data[optional_field]), timeout=1)

        return all(filled_required)

    def submit_signup_form(self) -> bool:
        submit = self.find_first(self.field_candidates("submit"), timeout=5, clickable=True)
        return bool(submit and self.safe_click(submit))

    def verify_success(self) -> bool:
        """Check for configured local success indicators or success URL fragments."""
        driver = self._require_driver()
        for indicator in self.config["success_indicators"]:
            locators = [
                (By.CLASS_NAME, indicator),
                (By.ID, indicator),
                (By.CSS_SELECTOR, f"[data-testid='{indicator}']"),
            ]
            if self.find_first(locators, timeout=1):
                return True

        current_url = driver.current_url.lower()
        return "success" in current_url or "welcome" in current_url

    def run_once(self, user_data: Optional[Mapping[str, str]] = None) -> SignupResult:
        """Open the configured local signup URL, fill, submit, and verify."""
        driver = self._require_driver()
        signup_url = self.config["signup_url"]
        if not self._is_local_url(signup_url):
            raise ConfigError("Only local signup URLs are allowed.")

        driver.get(signup_url)
        self.sleep_page_load()
        data = user_data or self.config["test_user"]
        submitted = self.fill_signup_form(data) and self.submit_signup_form()
        self.sleep_action()
        return SignupResult(submitted=submitted, success=self.verify_success(), url=driver.current_url)

    def run_with_retries(self, user_data: Optional[Mapping[str, str]] = None) -> SignupResult:
        """Run a local signup form test with bounded retry and session recovery."""
        attempts = self.config["retry_attempts"] + 1
        last_result = SignupResult(submitted=False, success=False, url=self.config["signup_url"])
        for attempt in range(attempts):
            try:
                last_result = self.run_once(user_data)
                if last_result.success:
                    return last_result
            except Exception as exc:  # deliberately recovers only test session health
                if self.is_invalid_session_error(exc):
                    self.refresh_driver_session(str(exc))
                else:
                    LOGGER.warning("Local signup form test attempt %s failed: %s", attempt + 1, exc)
            if attempt < attempts - 1:
                self._sleep_random("min_attempt_delay", "max_attempt_delay")
        return last_result

    def close(self) -> None:
        if self.driver is not None:
            self.driver.quit()
            self.driver = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run authorized local signup form QA tests.")
    parser.add_argument("--config", default="config.json", help="Path to config JSON.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    tester = SignupFormTester(config_path=args.config)
    try:
        result = tester.run_with_retries()
        LOGGER.info("Submitted=%s Success=%s URL=%s", result.submitted, result.success, result.url)
        return 0 if result.success else 1
    finally:
        tester.close()


if __name__ == "__main__":
    raise SystemExit(main())
