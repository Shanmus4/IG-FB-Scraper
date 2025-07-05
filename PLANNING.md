## Project Goal
Build a Node.js script using Puppeteer to scrape Instagram or Facebook profiles.

## Tech Stack
- Node.js
- Puppeteer
- `inquirer` package for user prompts
- `fs` for file system operations

## Folder Structure
- `scraper.js`: The main script.
- `cookies.txt`: File to store login cookies.
- `README.md`: Project documentation.
- `PLANNING.md`: This file.
- `TASKS.md`: Task log.

## Naming Conventions
- Functions: camelCase (e.g., `scrapeInstagram`)
- Variables: camelCase (e.g., `profileUrl`)

## Features
1.  **Interactive User Prompts:**
    - Ask for platform (Instagram/Facebook).
    - Ask for profile URL.
    - Ask for HTML report save path.
2.  **Authentication:**
    - Load cookies from `cookies.txt`.
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
5.  **General:**
    - Use `inquirer` for prompts.
    - Use `fs` for file operations.
    - Use realistic User-Agent.
    - Handle pagination for followers/following.
    - Log progress to the console.

## Current Status
All core features for scraping and report generation have been implemented and refined.