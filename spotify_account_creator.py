import os
import time
import random
import json
import logging
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Set
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    WebDriverException,
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

        if use_captcha_solver:
            load_dotenv()
            self.solver = TwoCaptcha(os.getenv('2CAPTCHA_API_KEY'))

        self.setup_driver()

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
            self.driver.get('https://www.spotify.com/signup')
            self.sleep_page_load()
            self._dismiss_cookie_banner()

            user_data = self.generate_random_data()
            logging.info(f"Attempting to create account with email: {user_data['email']}")

            email_field = self.wait_and_find_element(By.ID, 'email')
            if email_field:
                self.human_like_typing(email_field, user_data['email'])

            confirm_field = self.wait_and_find_element(By.ID, 'confirm')
            if confirm_field:
                self.human_like_typing(confirm_field, user_data['email'])

            password_field = self.wait_and_find_element(By.ID, 'password')
            if password_field:
                self.human_like_typing(password_field, user_data['password'])

            display_name_field = self.wait_and_find_element(By.ID, 'displayname')
            if display_name_field:
                self.human_like_typing(display_name_field, user_data['display_name'])

            day_field = self.wait_and_find_element(By.ID, 'day')
            if day_field:
                self.human_like_typing(day_field, user_data['birth_date'].split('-')[2])

            month_field = self.wait_and_find_element(By.ID, 'month')
            if month_field:
                self.human_like_typing(month_field, user_data['birth_date'].split('-')[1])

            year_field = self.wait_and_find_element(By.ID, 'year')
            if year_field:
                self.human_like_typing(year_field, user_data['birth_date'].split('-')[0])

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

            submit_button = self.wait_and_find_element(By.ID, 'register-button')
            if submit_button:
                self._safe_click(submit_button)

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
                return self.create_account(retry_count + 1, post_creation_mode=post_creation_mode)

            return False

        except Exception as e:
            logging.error(f"Error creating account: {str(e)}")

            if retry_count < self.config['retry_attempts']:
                logging.info(f"Retrying account creation (attempt {retry_count + 1})")
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
    # Example usage with proxy list
    proxy_list = [
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:8080",
        # Add more proxies as needed
    ]

    creator = SpotifyAccountCreator(
        use_proxy=True,  # Set to True if using proxy
        proxy_list=proxy_list,  # Add your proxy list here
        use_captcha_solver=False,  # Set to True if using 2Captcha
        config_path='config.json',  # Path to your config file
    )

    try:
        for i in range(5):
            logging.info(f"\nAttempting to create account {i+1}...")

            # Modes:
            # - account_only
            # - playlist_follow_artists
            # - playlist_follow_artists_play_repeat
            if creator.create_account(post_creation_mode=None):
                logging.info("Account created successfully!")
            else:
                logging.error("Failed to create account")

            delay = random.uniform(
                creator.config['delays']['min_attempt_delay'],
                creator.config['delays']['max_attempt_delay'],
            )
            logging.info(f"Waiting {delay:.2f} seconds before next attempt...")
            time.sleep(delay)

        creator.export_accounts(format='csv')

    finally:
        creator.close()
