import os
import time
import random
import json
import logging
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
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
        logging.StreamHandler()
    ]
)

class SpotifyAccountCreator:
    def __init__(self, 
                 use_proxy: bool = False, 
                 proxy_list: Optional[List[str]] = None,
                 use_captcha_solver: bool = False,
                 config_path: str = 'config.json'):
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
        default_config = {
            'delays': {
                'min_typing_delay': 0.1,
                'max_typing_delay': 0.3,
                'min_page_load_delay': 2,
                'max_page_load_delay': 4,
                'min_attempt_delay': 5,
                'max_attempt_delay': 10
            },
            'retry_attempts': 3,
            'success_indicators': [
                'success-message',
                'account-created',
                'welcome-page'
            ]
        }
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    return {**default_config, **json.load(f)}
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
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
        # Additional anti-detection measures
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
    
    def generate_random_data(self) -> Dict:
        """Generate random user data"""
        return {
            'email': self.fake.email(),
            'password': self.fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True),
            'display_name': self.fake.name(),
            'birth_date': self.fake.date_of_birth(minimum_age=18, maximum_age=60).strftime('%Y-%m-%d'),
            'gender': random.choice(['male', 'female', 'non-binary']),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def solve_captcha(self) -> Optional[str]:
        """Solve CAPTCHA if enabled"""
        if not self.use_captcha_solver:
            return None
            
        try:
            # Wait for CAPTCHA to be present
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'g-recaptcha'))
            )
            
            # Get the site key from the page
            site_key = self.driver.find_element(By.CLASS_NAME, 'g-recaptcha').get_attribute('data-sitekey')
            
            # Solve the captcha
            result = self.solver.recaptcha(
                sitekey=site_key,
                url=self.driver.current_url
            )
            
            return result['code']
        except Exception as e:
            logging.error(f"Error solving CAPTCHA: {str(e)}")
            return None
    
    def wait_and_find_element(self, by, value, timeout=10):
        """Wait for element to be present and return it"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            logging.warning(f"Timeout waiting for element: {value}")
            return None
    
    def human_like_typing(self, element, text):
        """Type text with human-like delays"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(
                self.config['delays']['min_typing_delay'],
                self.config['delays']['max_typing_delay']
            ))
    
    def verify_success(self) -> bool:
        """Verify if account creation was successful"""
        try:
            # Check for any success indicators
            for indicator in self.config['success_indicators']:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CLASS_NAME, indicator))
                    )
                    return True
                except TimeoutException:
                    continue
            
            # Check URL for success indicators
            current_url = self.driver.current_url
            if 'success' in current_url.lower() or 'welcome' in current_url.lower():
                return True
            
            return False
        except Exception as e:
            logging.error(f"Error verifying success: {str(e)}")
            return False
    
    def create_account(self, retry_count=0) -> bool:
        """Create a Spotify account with retry logic"""
        try:
            # Navigate to Spotify signup page
            self.driver.get('https://www.spotify.com/signup')
            time.sleep(random.uniform(
                self.config['delays']['min_page_load_delay'],
                self.config['delays']['max_page_load_delay']
            ))
            
            # Generate random user data
            user_data = self.generate_random_data()
            logging.info(f"Attempting to create account with email: {user_data['email']}")
            
            # Fill in the form with human-like typing
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
            
            # Select birth date
            day_field = self.wait_and_find_element(By.ID, 'day')
            if day_field:
                self.human_like_typing(day_field, user_data['birth_date'].split('-')[2])
            
            month_field = self.wait_and_find_element(By.ID, 'month')
            if month_field:
                self.human_like_typing(month_field, user_data['birth_date'].split('-')[1])
            
            year_field = self.wait_and_find_element(By.ID, 'year')
            if year_field:
                self.human_like_typing(year_field, user_data['birth_date'].split('-')[0])
            
            # Select gender
            try:
                gender_radio = self.wait_and_find_element(
                    By.XPATH, 
                    f"//label[contains(text(), '{user_data['gender']}')]"
                )
                if gender_radio:
                    gender_radio.click()
            except ElementClickInterceptedException:
                logging.warning("Could not click gender radio button")
            
            # Handle CAPTCHA if enabled
            if self.use_captcha_solver:
                captcha_response = self.solve_captcha()
                if captcha_response:
                    self.driver.execute_script(
                        f"document.getElementById('g-recaptcha-response').innerHTML='{captcha_response}'"
                    )
            
            # Submit the form
            submit_button = self.wait_and_find_element(By.ID, 'register-button')
            if submit_button:
                submit_button.click()
            
            # Wait and verify success
            time.sleep(5)  # Wait for page to load
            if self.verify_success():
                logging.info(f"Successfully created account: {user_data['email']}")
                self.accounts.append(user_data)
                return True
            else:
                logging.warning("Account creation might have failed - could not verify success")
                
                # Retry logic
                if retry_count < self.config['retry_attempts']:
                    logging.info(f"Retrying account creation (attempt {retry_count + 1})")
                    return self.create_account(retry_count + 1)
                
                return False
            
        except Exception as e:
            logging.error(f"Error creating account: {str(e)}")
            
            # Retry logic
            if retry_count < self.config['retry_attempts']:
                logging.info(f"Retrying account creation (attempt {retry_count + 1})")
                return self.create_account(retry_count + 1)
            
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
        config_path='config.json'  # Path to your config file
    )
    
    try:
        # Create multiple accounts
        for i in range(5):  # Change the number as needed
            logging.info(f"\nAttempting to create account {i+1}...")
            if creator.create_account():
                logging.info("Account created successfully!")
            else:
                logging.error("Failed to create account")
            
            # Random delay between attempts
            delay = random.uniform(
                creator.config['delays']['min_attempt_delay'],
                creator.config['delays']['max_attempt_delay']
            )
            logging.info(f"Waiting {delay:.2f} seconds before next attempt...")
            time.sleep(delay)
        
        # Export accounts
        creator.export_accounts(format='csv')
        
    finally:
        creator.close() 