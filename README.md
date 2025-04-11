# Spotify Account Creator

An automated tool for creating Spotify accounts using Python and Selenium. This tool is designed for educational purposes and automation testing.

## Author

**Letda Kes Dr. Sobri, S.Kom**  
Email: muhammadsobrimaulana31@gmail.com  
GitHub: [sobri3195](https://github.com/sobri3195)

## Features

- Automated Spotify account creation
- Random email and password generation
- Proxy support with rotation
- CAPTCHA solving integration (using 2Captcha)
- Export accounts to CSV or JSON format
- Anti-detection measures
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
    "success_indicators": [
        "success-message",
        "account-created",
        "welcome-page"
    ]
}
```

## Usage

Basic usage:
```python
from spotify_account_creator import SpotifyAccountCreator

# Create instance without proxy or CAPTCHA solver
creator = SpotifyAccountCreator()

# Create instance with proxy and CAPTCHA solver
creator = SpotifyAccountCreator(
    use_proxy=True,
    proxy_list=["http://proxy1.example.com:8080", "http://proxy2.example.com:8080"],
    use_captcha_solver=True
)

# Create accounts
for _ in range(5):
    if creator.create_account():
        print("Account created successfully!")
    
# Export accounts to CSV
creator.export_accounts(format='csv')

# Don't forget to close the browser
creator.close()
```

## Important Notes

- Use this tool responsibly and in accordance with Spotify's Terms of Service
- The tool includes random delays between account creation attempts
- Consider using proxies to avoid IP-based restrictions
- CAPTCHA solving requires a valid 2Captcha API key
- The tool includes anti-detection measures to make automation less detectable

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