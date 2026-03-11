# Spotify Account Creator

An automated tool for creating Spotify accounts using Python and Selenium. This tool is designed for educational purposes and automation testing.

## Author

**Letda Kes Dr. Sobri, S.Kom**  
Email: muhammadsobrimaulana31@gmail.com  
GitHub: [sobri3195](https://github.com/sobri3195)

## Features

- Automated Spotify account creation
- Optional post-creation onboarding:
  - Follow a target playlist
  - Follow each artist found in that playlist
  - (Optional) start playing the playlist and enable repeat
- Random email and password generation
- Proxy support with rotation
- CAPTCHA solving integration (using 2Captcha)
- Export accounts to CSV or JSON format
- Anti-detection measures (best-effort)
- Configurable settings
- Detailed logging

## Prerequisites

- Python 3.8 or higher
- Chrome browser installed
- (Optional) 2Captcha API key for CAPTCHA solving
- (Optional) Proxy server details

## Installation

1. Clone this repository:

```bash
git clone https://github.com/sobri3195/spotify-account-creator.git
cd spotify-account-creator
```

2. Install the required packages:

```bash
pip install -r requirements.txt
```

3. Configure your settings:

- Copy `.env.example` to `.env` and add your 2Captcha API key if using CAPTCHA solver
- Edit `config.json` to customize settings if needed

## Configuration

The tool uses two configuration files:

1. `.env` - For sensitive data:

```
2CAPTCHA_API_KEY=your_api_key_here
```

2. `config.json` - For general settings:

```json
{
  "delays": {
    "min_typing_delay": 0.1,
    "max_typing_delay": 0.3,
    "min_page_load_delay": 2,
    "max_page_load_delay": 4,
    "min_attempt_delay": 5,
    "max_attempt_delay": 10
  },
  "retry_attempts": 3,
  "post_creation": {
    "mode": "account_only",
    "playlist_url": "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID",
    "max_artists_to_follow": 25,
    "max_playlist_scrolls": 12
  }
}
```

### Post-creation modes

Set `post_creation.mode` (or pass `post_creation_mode` to `create_account(...)`) to one of:

- `account_only` (default)
- `playlist_follow_artists`
- `playlist_follow_artists_play_repeat`

`playlist_url` should be a full playlist URL, e.g. `https://open.spotify.com/playlist/<id>`.

## Usage

Basic usage:

```python
from spotify_account_creator import SpotifyAccountCreator

creator = SpotifyAccountCreator()

# Create an account only
creator.create_account(post_creation_mode="account_only")

# Create an account + follow playlist + follow artists
creator.create_account(post_creation_mode="playlist_follow_artists")

# Create an account + follow playlist + follow artists + play on repeat
creator.create_account(post_creation_mode="playlist_follow_artists_play_repeat")

creator.export_accounts(format="csv")
creator.close()
```

## CLI Usage (Improved UX)

You can now run the tool from terminal with clear options:

```bash
python spotify_account_creator.py --count 3 --mode playlist_follow_artists --export csv
```

Useful flags:

- `--count` Number of account creation attempts
- `--config` Path to config file (default: `config.json`)
- `--mode` Override `post_creation.mode` from config
- `--use-proxy` Enable proxy usage
- `--proxy` Add proxy URL (repeatable)
- `--captcha` Enable 2Captcha solver (requires `2CAPTCHA_API_KEY`)
- `--export` Export format (`csv` or `json`)

Example with proxies:

```bash
python spotify_account_creator.py --use-proxy --proxy http://127.0.0.1:8080 --count 2
```

## Important Notes

- Use this tool responsibly and in accordance with Spotify's Terms of Service
- The tool includes random delays between account creation attempts
- Consider using proxies to avoid IP-based restrictions
- CAPTCHA solving requires a valid 2Captcha API key
- Spotify UI changes frequently; selectors may require updates over time

## Support

If you find this tool useful and would like to support the development, consider making a donation:

[![Donate](https://img.shields.io/badge/Donate-Link-blue)](https://lynk.id/muhsobrimaulana)

## Disclaimer

This tool is for educational purposes only. The author is not responsible for any misuse of this tool. Please use it responsibly and in accordance with Spotify's Terms of Service.

## License

MIT License

Copyright (c) 2024 Letda Kes Dr. Sobri, S.Kom

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
