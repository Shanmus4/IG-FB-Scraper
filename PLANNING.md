## Project Goal
Build a Node.js script using Puppeteer to scrape Instagram or Facebook profiles.

## Tech Stack
- Node.js
- Puppeteer
- `inquirer` package for user prompts
- `fs` for file system operations

## Folder Structure
- `scraper.js`: The main script.
- `instagram_cookies.txt`: File to store Instagram login cookies.
- `facebook_cookies.txt`: File to store Facebook login cookies.
- `instagram_useragent.txt`: File to store Instagram User-Agent.
- `facebook_useragent.txt`: File to store Facebook User-Agent.
- `README.md`: Project documentation.
- `PLANNING.md`: This file.
- `TASKS.md`: Task log.
- `.gitignore`: Specifies files to be ignored by Git.
- `package.json`: Node.js project metadata and dependency list.
- `package-lock.json`: Records the exact dependency tree.

## Naming Conventions
- Functions: camelCase (e.g., `scrapeInstagram`)
- Variables: camelCase (e.g., `profileUrl`)

## Features
1.  **Interactive User Prompts:**
    - Ask for platform (Instagram/Facebook).
    - Ask for profile URL.
    - Ask for HTML report save path.
2.  **Authentication:**
    - Load cookies from `instagram_cookies.txt` or `facebook_cookies.txt` based on platform choice.
    - Attach cookies to Puppeteer requests.
3.  **Scraping:**
    - **Instagram:**
        - Extract numeric user ID.
        - Extract followers and following lists.
        - Extract latest 10 posts (caption, likes, comments).
    - **Facebook:**
        - Extract numeric Facebook ID.
        - Extract friends list.
        - Extract latest 10 posts (likes, comments).
4.  **HTML Report Generation:**
    - Generate a single, self-contained HTML file.
    - Clean design with inline CSS.
    - Sections for profile info, followers/friends, and posts.
    - **Instagram HTML report filenames are always generated using the Instagram username (never follower count or user ID).**
    - **Followers/following extraction uses robust scrolling and selector logic targeting the correct scrollable container and username anchors.**
    - Followers/following counts are shown next to their headings in the report.
    - Profile info counts (posts, followers, following) are robustly extracted from the Instagram page.
5.  **Stealth & Anti-Detection:**
    - Uses Puppeteer Stealth Plugin to avoid detection.
    - Reads User-Agent from a file (`instagram_useragent.txt` or `facebook_useragent.txt`) instead of prompting the user.
    - Robust auto-scrolling of followers/following dialogs to extract all users.
    - Randomized delays (2–8s) between actions to mimic human behavior.
    - Checks login status after navigation and before scraping.
6.  **General:**
    - Use `inquirer` for prompts (except User-Agent, which is read from file).
    - Use `fs` for file operations.
    - All support files (`instagram_cookies.txt`, `facebook_cookies.txt`, `instagram_useragent.txt`, `facebook_useragent.txt`) must be present in the project directory.

## Dependency Management
Dependencies are managed using `package.json` and `package-lock.json`, which are the standard for Node.js projects. A `requirements.txt` file is not used as it is specific to Python projects.

## Current Status
All core features for scraping and report generation have been implemented and refined. The project structure and documentation are complete and up-to-date. The script now reads User-Agent from a file, uses robust auto-scrolling to extract all followers/following, and requires all support files to be present in the project directory.