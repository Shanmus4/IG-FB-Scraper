# Social Media Scraper

A Python-based tool to scrape data from Instagram and Facebook profiles, generating beautiful HTML reports.

## Features

### Instagram Scraper
- Scrape profile information
- Download posts, stories, and highlights
- Get followers and following lists
- Generate interactive HTML reports

### Facebook Scraper
- Scrape public Facebook pages and profiles
- Extract posts, comments, and media
- Generate interactive HTML reports
- Export data to JSON/CSV formats
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
   pip install -r requirements.txt
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

## Facebook Scraper (Playwright + SingleFile)

This scraper uses Playwright to drive a full Chromium browser and the SingleFile extension to capture complete, self-contained HTML snapshots of Facebook pages (profile, about, friends, posts, photos, etc.).

Overview
- The script `Facebook/facebook.py` launches a persistent Chromium profile with a small controller extension that bundles SingleFile. Playwright opens pages, scrolls/expands content heuristically, and asks the extension to produce a single-file HTML capture.
- This approach is robust for capturing dynamic content that requires JavaScript (comments overlays, lazy-loaded media, etc.).

Prerequisites
- Python 3.8+
- Playwright Python package + browsers (Chromium recommended)
- The `SingleFile` folder must exist in the repository (it is included). The script copies `SingleFile/lib` into a temporary extension directory at runtime.

Install dependencies
1. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .\venv
.\venv\Scripts\Activate.ps1
```

2. Install Python requirements:

```powershell
pip install -r .\requirements.txt
```

3. Install Playwright browser binaries (required):

```powershell
python -m playwright install
# or to install only Chromium:
python -m playwright install chromium
```

Cookie setup (.env)
- The Facebook scraper authenticates by loading your browser cookies into the Playwright context. Create a `.env` file in the repository root or in the `Facebook/` folder (the script looks for `.env` at runtime). The `.env` should contain either:

- A single raw cookie header line (semicolon-separated key=value pairs), for example:

```text
mid=...; datr=...; sb=...; xs=...; c_user=...; fr=...
```

- Or a Netscape-format cookie dump (the script tries to be flexible). If you have the browser cookies in Developer Tools > Application > Cookies you can copy the cookie header from a request in the Network tab. The simplest method is to copy the full `Cookie` header string and paste it into `.env` as a single line.

Important: Treat `.env` as secret. Do NOT commit it.

How it works (brief)
- The script builds a small controller extension in `sf_playwright_ext/` that contains the SingleFile library from `SingleFile/lib/` plus a tiny `content_script.js` and `background.html`.
- Playwright launches Chromium with `--disable-extensions-except` and `--load-extension` pointing to the generated extension folder. The extension exposes a simple `window.postMessage` bridge so the script can ask the extension to produce a capture and receive the full HTML content.
- The script programmatically scrolls the page, expands "See more" links and comment overlays, opens reactions dialogs, and then requests a SingleFile capture for the current page or subsection.

Running the Facebook scraper (PowerShell)
1. From the repo root, with your virtualenv active and browsers installed, run:

```powershell
python Facebook\facebook.py --url "https://www.facebook.com/<username or profile.php?id=...>" --posts-limit 20
```

2. The script will:
- Build the controller extension under `sf_playwright_ext/` (overwrites if exists)
- Launch a visible Chromium instance (headful) so you can observe or interact if needed
- Load cookies into the browser context so Facebook sees you as logged in
- Visit the profile URL, scroll, expand content, and capture snapshots with SingleFile

3. Output
- Snapshots are saved to a profile-specific snapshots folder: `<profile_id>_snapshots/`
- A master HTML file named `{profile_id}_facebook.html` is generated at repo root and contains iframes referencing each snapshot for quick browsing.

Troubleshooting and tips
- If Playwright cannot find browsers or the script errors with browser-related exceptions, ensure you ran `python -m playwright install` successfully.
- If captures are missing or show the Facebook login page, your cookie is missing/invalid/expired. Refresh cookies in your browser and update `.env`.
- The extension uses Manifest v2 patterns to integrate SingleFile; if your Chromium/Playwright version changes extension APIs, you may need to update `facebook.py` extension builder (manifest contents).
- The scraping heuristics (text matches and xpath selectors) are brittle and tuned for the current Facebook layout; occasional UI updates can break extraction. If you see elements not being expanded, update the helper patterns in `facebook.py` (functions like `click_all_see_more` and `expand_all_comments`).

Security & legal
- Only use this tool on content you are authorized to access. Respect Facebook's Terms of Service, robots, and privacy laws.
- Delete `.env` and browser user data folder (`.playwright_user_data`) after use if you are on a shared or CI machine.


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
   - Solution: Run `pip install -r requirements.txt`

## Security

- Never commit your `.env` file or share it with others
- Be cautious when sharing HTML reports as they may contain sensitive information
- The script only accesses data that's visible when logged into your Instagram account
- Cookies are stored locally and only used for the session

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
