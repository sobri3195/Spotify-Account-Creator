import os
import time
import random
import json
import logging
import argparse
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Set
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    WebDriverException,
    InvalidSessionIdException,
)
from webdriver_manager.chrome import ChromeDriverManager
from faker import Faker
from dotenv import load_dotenv
from twocaptcha import TwoCaptcha

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spotify_creator.log'),
        logging.StreamHandler(),
    ],
)


POST_CREATION_MODE_ACCOUNT_ONLY = "account_only"
POST_CREATION_MODE_PLAYLIST_FOLLOW_ARTISTS = "playlist_follow_artists"
POST_CREATION_MODE_PLAYLIST_FOLLOW_ARTISTS_PLAY_REPEAT = "playlist_follow_artists_play_repeat"


class SpotifyAccountCreator:
    def __init__(
        self,
        use_proxy: bool = False,
        proxy_list: Optional[List[str]] = None,
        use_captcha_solver: bool = False,
        config_path: str = 'config.json',
    ):
        self.fake = Faker()
        self.use_proxy = use_proxy
        self.proxy_list = proxy_list or []
        self.current_proxy_index = 0
        self.use_captcha_solver = use_captcha_solver
        self.accounts = []
        self.config = self.load_config(config_path)
        self._validate_config()

        if use_captcha_solver:
            load_dotenv()
            captcha_key = os.getenv('2CAPTCHA_API_KEY')
            if not captcha_key:
                logging.warning("2CAPTCHA_API_KEY not found. CAPTCHA solver disabled.")
                self.use_captcha_solver = False
            else:
                self.solver = TwoCaptcha(captcha_key)

        self.setup_driver()

    def _validate_config(self):
        """Validate config values and self-heal obvious mistakes."""
        delays = self.config.get('delays', {})
        delay_pairs = [
            ('min_typing_delay', 'max_typing_delay'),
            ('min_page_load_delay', 'max_page_load_delay'),
            ('min_attempt_delay', 'max_attempt_delay'),
            ('min_action_delay', 'max_action_delay'),
            ('min_scroll_delay', 'max_scroll_delay'),
        ]

        for min_key, max_key in delay_pairs:
            min_value = float(delays.get(min_key, 0))
            max_value = float(delays.get(max_key, 0))
            if min_value < 0:
                min_value = 0
            if max_value < 0:
                max_value = 0
            if min_value > max_value:
                logging.warning(
                    "Invalid delay range for %s/%s. Swapping values.",
                    min_key,
                    max_key,
                )
                min_value, max_value = max_value, min_value
            delays[min_key] = min_value
            delays[max_key] = max_value

        retry_attempts = int(self.config.get('retry_attempts', 3))
        self.config['retry_attempts'] = max(0, retry_attempts)

        post_creation_cfg = self.config.get('post_creation', {})
        allowed_modes = {
            POST_CREATION_MODE_ACCOUNT_ONLY,
            POST_CREATION_MODE_PLAYLIST_FOLLOW_ARTISTS,
            POST_CREATION_MODE_PLAYLIST_FOLLOW_ARTISTS_PLAY_REPEAT,
        }
        mode = post_creation_cfg.get('mode', POST_CREATION_MODE_ACCOUNT_ONLY)
        if mode not in allowed_modes:
            logging.warning("Unknown post_creation.mode '%s'. Using account_only.", mode)
            post_creation_cfg['mode'] = POST_CREATION_MODE_ACCOUNT_ONLY

        post_creation_cfg['max_artists_to_follow'] = max(
            1,
            int(post_creation_cfg.get('max_artists_to_follow', 25)),
        )
        post_creation_cfg['max_playlist_scrolls'] = max(
            1,
            int(post_creation_cfg.get('max_playlist_scrolls', 12)),
        )
        self.config['post_creation'] = post_creation_cfg

    def load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""

        def deep_merge(base: Dict, override: Dict) -> Dict:
            merged = dict(base)
            for k, v in override.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k] = deep_merge(merged[k], v)
                else:
                    merged[k] = v
            return merged

        default_config = {
            'delays': {
                'min_typing_delay': 0.1,
                'max_typing_delay': 0.3,
                'min_page_load_delay': 2,
                'max_page_load_delay': 4,
                'min_attempt_delay': 5,
                'max_attempt_delay': 10,
                'min_action_delay': 0.8,
                'max_action_delay': 2.0,
                'min_scroll_delay': 0.8,
                'max_scroll_delay': 1.6,
            },
            'retry_attempts': 3,
            'success_indicators': [
                'success-message',
                'account-created',
                'welcome-page',
            ],
            'post_creation': {
                'mode': POST_CREATION_MODE_ACCOUNT_ONLY,
                'playlist_url': None,
                'max_artists_to_follow': 25,
                'max_playlist_scrolls': 12,
            },
        }

        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                return deep_merge(default_config, user_config)
            return default_config
        except Exception as e:
            logging.warning(f"Error loading config: {e}. Using default configuration.")
            return default_config

    def get_next_proxy(self) -> Optional[str]:
        """Get next proxy from the list"""
        if not self.proxy_list:
            return None

        proxy = self.proxy_list[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
        return proxy

    def setup_driver(self):
        chrome_options = webdriver.ChromeOptions()

        if self.use_proxy:
            proxy = self.get_next_proxy()
            if proxy:
                chrome_options.add_argument(f'--proxy-server={proxy}')
                logging.info(f"Using proxy: {proxy}")

        # Enhanced anti-detection measures
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )

        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options,
        )

        # Additional anti-detection measures
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")

    def _refresh_driver_session(self, reason: str = ""):
        if reason:
            logging.info("Refreshing browser session: %s", reason)

        old_driver = getattr(self, 'driver', None)
        if old_driver is not None:
            try:
                old_driver.quit()
            except Exception:
                pass

        self.setup_driver()

    @staticmethod
    def _is_proxy_connection_error(error: Exception) -> bool:
        msg = str(error).lower()
        return 'err_proxy_connection_failed' in msg or 'proxy connection failed' in msg

    @staticmethod
    def _is_invalid_session_error(error: Exception) -> bool:
        if isinstance(error, InvalidSessionIdException):
            return True
        msg = str(error).lower()
        return 'invalid session id' in msg or 'not connected to devtools' in msg

    def _sleep_random(self, min_seconds: float, max_seconds: float):
        time.sleep(random.uniform(min_seconds, max_seconds))

    def sleep_page_load(self):
        self._sleep_random(
            self.config['delays']['min_page_load_delay'],
            self.config['delays']['max_page_load_delay'],
        )

    def sleep_action(self):
        self._sleep_random(
            self.config['delays']['min_action_delay'],
            self.config['delays']['max_action_delay'],
        )

    def sleep_scroll(self):
        self._sleep_random(
            self.config['delays']['min_scroll_delay'],
            self.config['delays']['max_scroll_delay'],
        )

    def generate_random_data(self) -> Dict:
        """Generate random user data"""
        return {
            'email': self.fake.email(),
            'password': self.fake.password(
                length=12, special_chars=True, digits=True, upper_case=True, lower_case=True
            ),
            'display_name': self.fake.name(),
            'birth_date': self.fake.date_of_birth(minimum_age=18, maximum_age=60).strftime('%Y-%m-%d'),
            'gender': random.choice(['male', 'female', 'non-binary']),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def solve_captcha(self) -> Optional[str]:
        """Solve CAPTCHA if enabled"""
        if not self.use_captcha_solver:
            return None

        try:
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'g-recaptcha')))

            site_key = self.driver.find_element(By.CLASS_NAME, 'g-recaptcha').get_attribute('data-sitekey')

            result = self.solver.recaptcha(sitekey=site_key, url=self.driver.current_url)
            return result['code']
        except Exception as e:
            logging.error(f"Error solving CAPTCHA: {str(e)}")
            return None

    def wait_and_find_element(self, by, value, timeout=10):
        """Wait for element to be present and return it"""
        try:
            element = WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by, value)))
            return element
        except TimeoutException:
            return None

    def _find_first(self, candidates: List[Tuple[str, str]], timeout: int = 10, clickable: bool = False):
        last_error = None
        for by, value in candidates:
            try:
                wait = WebDriverWait(self.driver, timeout)
                condition = EC.element_to_be_clickable((by, value)) if clickable else EC.presence_of_element_located((by, value))
                return wait.until(condition)
            except TimeoutException as e:
                last_error = e
                continue
        if last_error:
            return None
        return None

    def _safe_click(self, element) -> bool:
        if element is None:
            return False
        try:
            element.click()
            return True
        except (ElementClickInterceptedException, WebDriverException):
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False

    def _safe_clear(self, element):
        if element is None:
            return
        try:
            element.clear()
        except Exception:
            pass
        try:
            element.send_keys(Keys.CONTROL, 'a')
            element.send_keys(Keys.DELETE)
        except Exception:
            pass
        try:
            self.driver.execute_script("arguments[0].value='';", element)
        except Exception:
            pass

    def _fill_field(self, candidates: List[Tuple[str, str]], value: str, timeout: int = 10) -> bool:
        field = self._find_first(candidates, timeout=timeout)
        if not field:
            return False

        self._safe_clear(field)
        self.human_like_typing(field, value)
        return True

    def _fill_field_js_fallback(self, candidates: List[Tuple[str, str]], value: str, timeout: int = 10) -> bool:
        """Fallback for modern controlled inputs that ignore send_keys.

        Some signup forms now rely on JS frameworks that only register values when
        bubbling input/change events are dispatched.
        """
        field = self._find_first(candidates, timeout=timeout)
        if not field:
            return False

        try:
            self.driver.execute_script(
                """
                const el = arguments[0];
                const val = arguments[1];
                el.focus();
                el.value = val;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.blur();
                """,
                field,
                value,
            )
            return True
        except Exception:
            return False

    def _fill_field_resilient(self, candidates: List[Tuple[str, str]], value: str, timeout: int = 10) -> bool:
        if self._fill_field(candidates, value, timeout=timeout):
            return True
        return self._fill_field_js_fallback(candidates, value, timeout=timeout)

    def _click_next_step(self) -> bool:
        """Click the intermediate signup step button (Next/Suivant)."""
        next_button = self._find_first(
            [
                (By.CSS_SELECTOR, "button[data-encore-id='buttonPrimary']"),
                (By.XPATH, "//button[contains(., 'Next')]"),
                (By.XPATH, "//button[contains(., 'Suivant')]"),
                (By.XPATH, "//button[contains(., 'Continue')]"),
            ],
            timeout=8,
            clickable=True,
        )
        if not next_button:
            return False
        if not self._safe_click(next_button):
            return False

        # Wait until a known field from the next step is visible.
        step_two_field = self._find_first(
            self._field_candidates('password') + self._field_candidates('display_name'),
            timeout=8,
        )
        return step_two_field is not None

    @staticmethod
    def _field_candidates(field_name: str) -> List[Tuple[str, str]]:
        candidates = {
            'email': [
                (By.ID, 'email'),
                (By.NAME, 'email'),
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[autocomplete='email']"),
                (By.CSS_SELECTOR, "input[data-testid='email-input']"),
            ],
            'confirm_email': [
                (By.ID, 'confirm'),
                (By.NAME, 'confirm'),
                (By.CSS_SELECTOR, "input[name='confirm_email']"),
                (By.CSS_SELECTOR, "input[data-testid='confirm-email-input']"),
            ],
            'password': [
                (By.ID, 'password'),
                (By.NAME, 'password'),
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.CSS_SELECTOR, "input[autocomplete='new-password']"),
                (By.CSS_SELECTOR, "input[data-testid='password-input']"),
            ],
            'display_name': [
                (By.ID, 'displayname'),
                (By.NAME, 'displayname'),
                (By.NAME, 'display_name'),
                (By.CSS_SELECTOR, "input[autocomplete='nickname']"),
                (By.CSS_SELECTOR, "input[data-testid='display-name-input']"),
            ],
            'day': [
                (By.ID, 'day'),
                (By.NAME, 'day'),
                (By.NAME, 'birth_day'),
                (By.CSS_SELECTOR, "input[placeholder='DD']"),
                (By.CSS_SELECTOR, "input[data-testid='day-input']"),
            ],
            'month': [
                (By.ID, 'month'),
                (By.NAME, 'month'),
                (By.NAME, 'birth_month'),
                (By.CSS_SELECTOR, "select[data-testid='month-select']"),
            ],
            'year': [
                (By.ID, 'year'),
                (By.NAME, 'year'),
                (By.NAME, 'birth_year'),
                (By.CSS_SELECTOR, "input[placeholder='YYYY']"),
                (By.CSS_SELECTOR, "input[data-testid='year-input']"),
            ],
        }
        return candidates.get(field_name, [])

    def _select_dropdown_value(self, candidates: List[Tuple[str, str]], value: str, timeout: int = 10) -> bool:
        field = self._find_first(candidates, timeout=timeout)
        if not field:
            return False

        try:
            Select(field).select_by_value(value)
            return True
        except Exception:
            try:
                Select(field).select_by_visible_text(str(int(value)))
                return True
            except Exception:
                return False

    def human_like_typing(self, element, text):
        """Type text with human-like delays"""
        for char in text:
            element.send_keys(char)
            self._sleep_random(
                self.config['delays']['min_typing_delay'],
                self.config['delays']['max_typing_delay'],
            )

    def _dismiss_cookie_banner(self):
        cookie_button = self._find_first(
            [
                (By.ID, 'onetrust-accept-btn-handler'),
                (By.XPATH, "//button[contains(., 'Accept')]"),
                (By.XPATH, "//button[contains(., 'I agree')]"),
            ],
            timeout=3,
            clickable=True,
        )
        if cookie_button:
            self._safe_click(cookie_button)
            self.sleep_action()

    def verify_success(self) -> bool:
        """Verify if account creation was successful"""
        try:
            for indicator in self.config['success_indicators']:
                try:
                    WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, indicator)))
                    return True
                except TimeoutException:
                    continue

            current_url = self.driver.current_url
            if 'success' in current_url.lower() or 'welcome' in current_url.lower():
                return True

            return False
        except Exception as e:
            logging.error(f"Error verifying success: {str(e)}")
            return False

    def _normalize_spotify_url(self, href: str) -> str:
        if href.startswith('http://') or href.startswith('https://'):
            return href.split('?')[0]
        return urljoin('https://open.spotify.com', href.split('?')[0])

    def _collect_artist_urls_from_playlist(self, max_artists: int, max_scrolls: int) -> List[str]:
        seen: Set[str] = set()
        last_count = 0

        for _ in range(max_scrolls):
            links = self.driver.find_elements(
                By.CSS_SELECTOR,
                'a[href^="/artist/"], a[href*="open.spotify.com/artist/"]',
            )
            for link in links:
                href = link.get_attribute('href')
                if not href:
                    continue
                if '/artist/' not in href:
                    continue
                seen.add(self._normalize_spotify_url(href))
                if len(seen) >= max_artists:
                    break

            if len(seen) >= max_artists:
                break

            self.driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
            self.sleep_scroll()

            if len(seen) == last_count:
                break
            last_count = len(seen)

        return list(seen)

    def _follow_current_page_entity(self) -> bool:
        """Click a Follow/Save button if present; attempts to avoid toggling unfollow."""
        follow_button = self._find_first(
            [
                (By.CSS_SELECTOR, 'button[data-testid="follow-button"]'),
                (By.CSS_SELECTOR, 'button[aria-label*="Follow"]'),
                (By.CSS_SELECTOR, 'button[aria-label*="Save"]'),
                (By.XPATH, "//button[contains(., 'Follow')]"),
                (By.XPATH, "//button[contains(., 'Save')]"),
            ],
            timeout=10,
            clickable=True,
        )
        if not follow_button:
            return False

        aria = (follow_button.get_attribute('aria-label') or '').lower()
        txt = (follow_button.text or '').lower()

        # Avoid toggling if it looks like we're already following/saved.
        already = any(s in aria for s in ['following', 'remove', 'saved', 'unfollow']) or 'following' in txt
        if already:
            return False

        return self._safe_click(follow_button)

    def follow_playlist_and_artists(self, playlist_url: str) -> Dict:
        """Follow a playlist and follow each artist found on the playlist page."""
        stats = {
            'playlist_followed': False,
            'artists_followed': 0,
        }

        self.driver.get(playlist_url)
        self.sleep_page_load()
        self._dismiss_cookie_banner()

        try:
            stats['playlist_followed'] = bool(self._follow_current_page_entity())
        except Exception:
            stats['playlist_followed'] = False

        max_artists = int(self.config.get('post_creation', {}).get('max_artists_to_follow', 25) or 25)
        max_scrolls = int(self.config.get('post_creation', {}).get('max_playlist_scrolls', 12) or 12)

        artist_urls = self._collect_artist_urls_from_playlist(max_artists=max_artists, max_scrolls=max_scrolls)
        if not artist_urls:
            logging.warning("No artist URLs found on the playlist page")
            return stats

        original_handle = self.driver.current_window_handle

        for url in artist_urls:
            try:
                self.driver.execute_script("window.open(arguments[0], '_blank');", url)
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.sleep_page_load()
                self._dismiss_cookie_banner()

                if self._follow_current_page_entity():
                    stats['artists_followed'] += 1

                self.sleep_action()
            except Exception as e:
                logging.warning(f"Failed to follow artist {url}: {e}")
            finally:
                try:
                    if self.driver.current_window_handle != original_handle:
                        self.driver.close()
                        self.driver.switch_to.window(original_handle)
                except Exception:
                    try:
                        self.driver.switch_to.window(original_handle)
                    except Exception:
                        pass

        return stats

    def play_playlist_on_repeat(self, playlist_url: str) -> Dict:
        stats = {
            'playback_started': False,
            'repeat_enabled': False,
        }

        self.driver.get(playlist_url)
        self.sleep_page_load()
        self._dismiss_cookie_banner()

        play_button = self._find_first(
            [
                (By.CSS_SELECTOR, 'button[data-testid="play-button"]'),
                (By.CSS_SELECTOR, 'button[aria-label*="Play"]'),
                (By.XPATH, "//button[contains(@aria-label, 'Play')]")
            ],
            timeout=10,
            clickable=True,
        )
        if play_button and self._safe_click(play_button):
            stats['playback_started'] = True
            self.sleep_action()

        repeat_button = self._find_first(
            [
                (By.CSS_SELECTOR, 'button[data-testid="control-button-repeat"]'),
                (By.CSS_SELECTOR, 'button[aria-label*="Repeat"]'),
            ],
            timeout=10,
            clickable=True,
        )

        if repeat_button:
            aria_before = (repeat_button.get_attribute('aria-label') or '').lower()
            if 'disable repeat' in aria_before or 'repeat on' in aria_before:
                stats['repeat_enabled'] = True
                return stats

            if self._safe_click(repeat_button):
                self.sleep_action()
                try:
                    aria_after = (repeat_button.get_attribute('aria-label') or '').lower()
                    stats['repeat_enabled'] = 'disable repeat' in aria_after or 'repeat on' in aria_after
                except Exception:
                    stats['repeat_enabled'] = True

        return stats

    def perform_post_creation_actions(self, mode: Optional[str] = None, playlist_url: Optional[str] = None) -> Dict:
        mode = mode or self.config.get('post_creation', {}).get('mode', POST_CREATION_MODE_ACCOUNT_ONLY)
        playlist_url = playlist_url or self.config.get('post_creation', {}).get('playlist_url')

        result = {
            'post_creation_mode': mode,
            'playlist_url': playlist_url,
            'playlist_followed': False,
            'artists_followed': 0,
            'playback_started': False,
            'repeat_enabled': False,
        }

        if mode == POST_CREATION_MODE_ACCOUNT_ONLY:
            return result

        if not playlist_url:
            logging.warning("Post-creation mode requires a playlist_url, but none was provided")
            return result

        try:
            follow_stats = self.follow_playlist_and_artists(playlist_url)
            result.update(follow_stats)
        except Exception as e:
            logging.warning(f"Post-creation follow actions failed: {e}")

        if mode == POST_CREATION_MODE_PLAYLIST_FOLLOW_ARTISTS_PLAY_REPEAT:
            try:
                play_stats = self.play_playlist_on_repeat(playlist_url)
                result.update(play_stats)
            except Exception as e:
                logging.warning(f"Post-creation playback actions failed: {e}")

        return result

    def create_account(self, retry_count: int = 0, post_creation_mode: Optional[str] = None) -> bool:
        """Create a Spotify account with retry logic.

        post_creation_mode:
          - account_only
          - playlist_follow_artists
          - playlist_follow_artists_play_repeat
        """

        try:
            if getattr(self, 'driver', None) is None:
                self.setup_driver()

            self.driver.get('https://www.spotify.com/signup')
            self.sleep_page_load()
            self._dismiss_cookie_banner()

            user_data = self.generate_random_data()
            logging.info(f"Attempting to create account with email: {user_data['email']}")

            birth_year, birth_month, birth_day = user_data['birth_date'].split('-')

            email_filled = self._fill_field_resilient(self._field_candidates('email'), user_data['email'])
            if not email_filled:
                logging.warning("Email field was not found. UI layout may have changed.")

            self._click_next_step()

            required_fields = [
                self._fill_field_resilient(self._field_candidates('confirm_email'), user_data['email']),
                self._fill_field_resilient(self._field_candidates('password'), user_data['password']),
                self._fill_field_resilient(self._field_candidates('display_name'), user_data['display_name']),
                self._fill_field_resilient(self._field_candidates('day'), birth_day),
                self._fill_field_resilient(self._field_candidates('year'), birth_year),
            ]

            month_filled = self._select_dropdown_value(
                self._field_candidates('month'),
                str(int(birth_month)),
            )
            if not month_filled:
                month_filled = self._fill_field_resilient(self._field_candidates('month'), birth_month)
            required_fields.append(month_filled)

            if not all(required_fields):
                logging.warning("One or more signup fields were not found. UI layout may have changed.")

            try:
                gender_radio = self.wait_and_find_element(
                    By.XPATH,
                    f"//label[contains(text(), '{user_data['gender']}')]",
                )
                if gender_radio:
                    self._safe_click(gender_radio)
            except ElementClickInterceptedException:
                logging.warning("Could not click gender radio button")

            if self.use_captcha_solver:
                captcha_response = self.solve_captcha()
                if captcha_response:
                    self.driver.execute_script(
                        "document.getElementById('g-recaptcha-response').innerHTML=arguments[0]",
                        captcha_response,
                    )

            submit_button = self._find_first(
                [
                    (By.ID, 'register-button'),
                    (By.CSS_SELECTOR, "button[data-testid='submit']"),
                    (By.XPATH, "//button[@type='submit']"),
                ],
                timeout=10,
                clickable=True,
            )
            if submit_button:
                self._safe_click(submit_button)
            else:
                logging.error("Submit button not found. Cannot continue account creation.")
                return False

            time.sleep(5)
            if self.verify_success():
                logging.info(f"Successfully created account: {user_data['email']}")

                post_creation_result = {}
                try:
                    post_creation_result = self.perform_post_creation_actions(mode=post_creation_mode)
                except Exception as e:
                    logging.warning(f"Post-creation actions failed: {e}")

                user_data.update(post_creation_result)
                self.accounts.append(user_data)

                return True

            logging.warning("Account creation might have failed - could not verify success")

            if retry_count < self.config['retry_attempts']:
                logging.info(f"Retrying account creation (attempt {retry_count + 1})")
                self._sleep_random(
                    self.config['delays']['min_attempt_delay'],
                    self.config['delays']['max_attempt_delay'],
                )
                return self.create_account(retry_count + 1, post_creation_mode=post_creation_mode)

            return False

        except Exception as e:
            logging.error(f"Error creating account: {str(e)}")

            if self._is_proxy_connection_error(e) or self._is_invalid_session_error(e):
                self._refresh_driver_session(reason='webdriver session became unusable')

            if retry_count < self.config['retry_attempts']:
                logging.info(f"Retrying account creation (attempt {retry_count + 1})")
                self._sleep_random(
                    self.config['delays']['min_attempt_delay'],
                    self.config['delays']['max_attempt_delay'],
                )
                return self.create_account(retry_count + 1, post_creation_mode=post_creation_mode)

            return False

    def export_accounts(self, format='csv'):
        """Export created accounts to file"""
        if not self.accounts:
            logging.warning("No accounts to export!")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format.lower() == 'csv':
            df = pd.DataFrame(self.accounts)
            df.to_csv(f'spotify_accounts_{timestamp}.csv', index=False)
            logging.info(f"Accounts exported to spotify_accounts_{timestamp}.csv")
        else:
            with open(f'spotify_accounts_{timestamp}.json', 'w') as f:
                json.dump(self.accounts, f, indent=4)
            logging.info(f"Accounts exported to spotify_accounts_{timestamp}.json")

    def close(self):
        """Close the browser"""
        try:
            self.driver.quit()
        except Exception as e:
            logging.error(f"Error closing browser: {str(e)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Spotify Account Creator (educational automation testing tool).'
    )
    parser.add_argument('--count', type=int, default=1, help='Number of account creation attempts.')
    parser.add_argument('--config', default='config.json', help='Path to config JSON file.')
    parser.add_argument('--proxy', action='append', default=[], help='Proxy URL. Can be set multiple times.')
    parser.add_argument('--use-proxy', action='store_true', help='Enable proxy usage.')
    parser.add_argument('--captcha', action='store_true', help='Enable 2Captcha integration.')
    parser.add_argument(
        '--mode',
        choices=[
            POST_CREATION_MODE_ACCOUNT_ONLY,
            POST_CREATION_MODE_PLAYLIST_FOLLOW_ARTISTS,
            POST_CREATION_MODE_PLAYLIST_FOLLOW_ARTISTS_PLAY_REPEAT,
        ],
        default=None,
        help='Post-creation mode override.',
    )
    parser.add_argument('--export', choices=['csv', 'json'], default='csv', help='Export format.')
    args = parser.parse_args()

    creator = SpotifyAccountCreator(
        use_proxy=args.use_proxy,
        proxy_list=args.proxy,
        use_captcha_solver=args.captcha,
        config_path=args.config,
    )

    success_count = 0
    try:
        for i in range(max(1, args.count)):
            logging.info("\n[%s/%s] Starting account creation attempt...", i + 1, max(1, args.count))

            if creator.create_account(post_creation_mode=args.mode):
                success_count += 1
                logging.info("Attempt successful (%s/%s).", success_count, i + 1)
            else:
                logging.error("Attempt failed (%s/%s).", i + 1, max(1, args.count))

            if i + 1 < max(1, args.count):
                delay = random.uniform(
                    creator.config['delays']['min_attempt_delay'],
                    creator.config['delays']['max_attempt_delay'],
                )
                logging.info("Waiting %.2f seconds before next attempt...", delay)
                time.sleep(delay)

        creator.export_accounts(format=args.export)
        logging.info("Finished. Success rate: %s/%s", success_count, max(1, args.count))
    finally:
        creator.close()
