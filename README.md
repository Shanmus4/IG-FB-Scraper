# Social Media Scraper

A powerful tool to scrape and generate comprehensive reports from social media platforms. Currently supports Instagram, with Facebook support coming soon.

## Features

- **Instagram Scraper**: Generate detailed HTML reports of Instagram profiles
- **Dark-Themed UI**: Clean, readable interface for viewing scraped data
- **Self-Contained**: HTML reports include all media and data
- **Easy to Use**: Simple command-line interface

## Table of Contents
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Instagram Scraper](#instagram-scraper)
  - [Getting Instagram Cookies](#getting-instagram-cookies)
  - [Configuration](#configuration)
  - [API Hashes](#api-hashes)
- [Facebook Scraper](#facebook-scraper-coming-soon)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [License](#license)

## Installation

1. Clone or download this repository
2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r Instagram/requirements.txt
   ```

## Quick Start

1. Navigate to the project directory
2. Run the launcher:
   ```bash
   # On Windows
   .\run_scraper.bat
   
   # On macOS/Linux
   python main.py
   ```
3. Select the platform you want to scrape (Instagram or Facebook)
4. Follow the on-screen instructions

## Instagram Scraper

The Instagram scraper generates a comprehensive HTML report containing:
- Profile information (username, bio, followers, following)
- Recent posts with captions, likes, and comments
- Tagged posts
- Followers and following lists (up to the configured limit)

### Getting Instagram Cookies

1. Log in to Instagram in your web browser
2. Open Developer Tools (F12 or right-click → Inspect)
3. Go to the Network tab
4. Visit any Instagram page (like your feed)
5. Click on any request to `www.instagram.com` in the Network tab
6. In the Headers tab, find the `cookie` header
7. Copy the entire cookie string
8. Create a `.env` file in the Instagram folder with the cookie:
   ```
   INSTAGRAM_COOKIE=your_cookie_string_here
   ```
   
   Or you can paste just the cookie string directly into the file:
   ```
   mid=...; ig_did=...; csrftoken=...; ds_user_id=...; sessionid=...
   ```

### Configuration

You can adjust the following settings in `Instagram/insta.py`:

```python
# Limits
MAX_FOLLOWS = 400           # Maximum number of followers/following to fetch
PAGE_SIZE_FOLLOWS = 50      # Number of follows per API request
MAX_POSTS = 1000000         # Maximum posts to fetch (effectively no limit)
MAX_TAGGED = 1000000        # Maximum tagged posts to fetch
MAX_LIKES_PER_POST = 1000   # Maximum likes to fetch per post
PAGE_SIZE_LIKES = 50        # Number of likes per API request
MAX_COMMENTS_PER_POST = 1000 # Maximum comments to fetch per post
PAGE_SIZE_COMMENTS = 50     # Number of comments per API request

# Timing (in seconds)
SLEEP_MIN = 0.7            # Minimum delay between requests
SLEEP_MAX = 1.5            # Maximum delay between requests
```

### API Hashes

The Instagram scraper uses GraphQL query hashes to access different endpoints. These hashes may change when Instagram updates their API. If you encounter issues, you may need to update these hashes in `Instagram/insta.py`:

```python
# Common query_hash values (update these if Instagram changes them)
HASH_FOLLOWERS = "c76146de99bb02f6415203be841dd25a"
HASH_FOLLOWING = "d04b0a864b4b54837c0d870b0e77e076"
HASH_LIKES = "d5d763b1e2acf209d62d22d184488e57"
HASH_COMMENTS = "bc3296d1ce80a24b1b6e40b1e72903f5"
HASH_TAGGED = "ff260833edf142911047af6024eb634a"
```

To find updated hashes:
1. Log in to Instagram in your browser
2. Open Developer Tools (F12)
3. Go to the Network tab
4. Perform the action you're having trouble with (e.g., viewing followers)
5. Look for requests to `graphql/query/`
6. The `query_hash` parameter will contain the current hash

## Facebook Scraper (Coming Soon)

Facebook integration is planned for a future release. This section will be updated with documentation when available.

## Troubleshooting

### Common Issues

1. **Invalid or expired cookie**
   - Symptoms: Non-JSON responses or login page HTML
   - Solution: Get a fresh cookie from your browser

2. **Rate limiting**
   - Symptoms: 429 errors or temporary blocks
   - Solution: Increase the delay between requests in the configuration

3. **API changes**
   - Symptoms: 404 errors or unexpected responses
   - Solution: Update the query hashes in the script

4. **Missing dependencies**
   - Symptoms: Import errors when running the script
   - Solution: Run `pip install -r Instagram/requirements.txt`

## Security

- Never commit your `.env` file or share it with others
- Be cautious when sharing HTML reports as they may contain sensitive information
- The script only accesses data that's visible when logged into your Instagram account
- Cookies are stored locally and only used for the session

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
