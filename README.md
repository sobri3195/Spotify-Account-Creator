# SignupFormTester

SignupFormTester is a safe Selenium QA automation framework for testing signup forms on systems you own or are explicitly authorized to test. It is designed for local/mock form testing and defaults to `http://localhost:8000/signup`.

## Safety warning

Use this project only for authorized QA on owned systems. It must not be used to create accounts on third-party services, bypass VPN/proxy checks, bypass bot detection, bypass CAPTCHA, avoid rate limits, or manipulate engagement on any platform.

This refactor intentionally excludes:

- Proxy rotation or proxy configuration.
- Anti-detection browser fingerprint changes.
- `navigator.webdriver` spoofing.
- CAPTCHA solver integrations or CAPTCHA token injection.
- Fake third-party account export.
- Post-creation actions such as following artists/playlists or playing content.

## What it does

The framework keeps only safe QA utilities:

- JSON config loading and validation.
- Local-only signup URL validation, defaulting to `http://localhost:8000/signup`.
- Delay range sanitization.
- Retry attempt sanitization.
- Candidate selector mapping for common signup fields.
- Safe click and safe clear helpers.
- Resilient field filling.
- WebDriver session recovery for invalid Selenium sessions.

## Project layout

```text
signup_form_tester.py          # Safe Selenium QA framework
config.json                    # Example local/mock test configuration
tests/test_signup_form_tester.py
tests/fixtures/signup.html     # Mock signup page fixture
requirements.txt
```

## Install

```bash
python -m pip install -r requirements.txt
```

## Run unit tests

```bash
python -m pytest
```

The unit tests focus on config validation, selector mapping, safe local URL behavior, and the mock fixture. They do not create third-party accounts or contact third-party signup services.

## Run against the mock fixture

The default config points to `http://localhost:8000/signup`. To serve the included fixture at that route, run a simple local server from the `tests/fixtures` directory and map `/signup` to `signup.html` with your preferred development server.

A simpler option is to set `signup_url` in `config.json` to the fixture file URL, for example:

```json
{
  "signup_url": "file:///absolute/path/to/Spotify-Account-Creator/tests/fixtures/signup.html"
}
```

Then run:

```bash
python signup_form_tester.py --config config.json
```

## Example config

```json
{
  "signup_url": "http://localhost:8000/signup",
  "browser": {
    "headless": false,
    "window_size": "1280,900",
    "page_load_timeout": 20
  },
  "delays": {
    "min_typing_delay": 0.0,
    "max_typing_delay": 0.05,
    "min_page_load_delay": 0.1,
    "max_page_load_delay": 0.3,
    "min_attempt_delay": 0.1,
    "max_attempt_delay": 0.3,
    "min_action_delay": 0.0,
    "max_action_delay": 0.1
  },
  "retry_attempts": 2,
  "success_indicators": ["success-message", "signup-success", "account-created"],
  "test_user": {
    "email": "qa@example.test",
    "password": "CorrectHorseBatteryStaple!23",
    "display_name": "QA Tester",
    "day": "12",
    "month": "5",
    "year": "1995"
  }
}
```

## Development notes

- Keep targets local, such as `localhost`, `127.0.0.1`, `::1`, or a `file://` fixture URL.
- Keep test data synthetic and limited to systems you control.
- Do not add evasion, bypass, proxy rotation, CAPTCHA solving, third-party account creation, or engagement automation features.
