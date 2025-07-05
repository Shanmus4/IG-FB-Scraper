# Instagram & Facebook Scraper

This project provides a Node.js script utilizing Puppeteer to automate the scraping of public profile data from Instagram or Facebook. It allows users to extract information such as user IDs, follower/following/friends lists, and recent post details, generating a clean HTML report for easy viewing.

## Repository

[GitHub Repository Link](https://github.com/Shanmus4/IG-FB-Scraper.git)

## Live Deployment

[Live Deployment Link](YOUR_LIVE_DEPLOYMENT_LINK_HERE)

## Local Setup Guide

To set up and run this project locally, follow these steps:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Shanmus4/IG-FB-Scraper.git
    cd "IG FB Scraper"
    ```

2.  **Install Node.js:**
    Ensure you have Node.js installed on your system. You can download it from [nodejs.org](https://nodejs.org/).

3.  **Install Dependencies:**
    Navigate to the project's root directory in your terminal and install the required Node.js packages. Dependencies are managed via `package.json`.
    ```bash
    npm install
    npm install puppeteer-extra puppeteer-extra-plugin-stealth
    ```

4.  **Configure Cookies:**
    This script relies on your authenticated browser session to scrape data. You need to provide your login cookies in separate files. This process involves using your browser's Developer Tools to extract the `Cookie` header.
    - For Instagram: Save your cookie string in `instagram_cookies.txt`.
    - For Facebook: Save your cookie string in `facebook_cookies.txt`.

5.  **Configure User-Agent:**
    - For Instagram: Save your real browser User-Agent string in `instagram_useragent.txt`.
    - For Facebook: Save your real browser User-Agent string in `facebook_useragent.txt`.
    - These files must be in the same directory as `scraper.js`.

## Usage & Features

- **Stealth Mode:** The script uses Puppeteer Stealth Plugin to evade bot detection and mimic real browser behavior.
- **User-Agent from File:** The script reads your User-Agent from a file, not from a prompt. You must create `instagram_useragent.txt` or `facebook_useragent.txt` as appropriate.
- **Robust Auto-Scrolling:** Followers and following dialogs are auto-scrolled to the end, ensuring all users are loaded and extracted (no manual scrolling needed).
- **Full Data Extraction:** All followers, following, posts, likers, commenters, and tagged posts are extracted automatically.
- **Login Check:** The script checks if you are logged in after loading the profile. If not, it will warn you and exit.

## Commands to Run Locally

Once setup is complete, run the script from the project root:

```bash
node scraper.js
```

The script will guide you through interactive prompts to select the platform, provide the profile URL, and specify the directory for the HTML report. User-Agent and cookies are read from files.

## Troubleshooting
- If you see a login page in the Puppeteer window, your cookies or User-Agent are invalid or expired. Get fresh ones from your browser.
- If you get a `MODULE_NOT_FOUND` error, make sure you have installed all dependencies as described above.
- If you see only a few followers/following, check that your cookies and User-Agent are valid and that the dialog is scrolling (it should scroll automatically).

## Deployment Guide

This is a local scraping script and is not designed for direct web deployment. If you wish to deploy a similar service, consider a server-side application that handles Puppeteer execution and secure cookie management. For continuous integration/continuous deployment (CI/CD) setups, you would typically configure your CI/CD pipeline to run `npm install` and then `node scraper.js` within a suitable environment.

## Technical Overview

### Architecture

The project follows a simple client-side automation architecture:
-   **User Interface:** Interactive command-line prompts via `inquirer`.
-   **Browser Automation:** Puppeteer controls a headless (or headful for debugging) Chromium instance.
-   **Data Source:** Instagram or Facebook public profile pages, accessed via an authenticated session.
-   **Output:** A self-contained HTML file generated using Node.js `fs` module.

### Folder Structure

```
IG FB Scraper/
├── scraper.js        # Main script containing all logic
├── instagram_cookies.txt # Stores Instagram raw cookie string (ignored by Git)
├── facebook_cookies.txt  # Stores Facebook raw cookie string (ignored by Git)
├── instagram_useragent.txt # Stores Instagram real User-Agent string (ignored by Git)
├── facebook_useragent.txt  # Stores Facebook real User-Agent string (ignored by Git)
├── README.md         # Project documentation (this file)
├── PLANNING.md       # Project planning, goals, and technical details
├── TASKS.md          # Task log and progress tracking
├── .gitignore        # Specifies files to be ignored by Git (e.g., cookies.txt, node_modules/)
├── package.json      # Node.js project metadata and dependencies
└── package-lock.json # Records the exact dependency tree
```

### Technologies Used

-   **Node.js:** JavaScript runtime environment.
-   **Puppeteer:** A Node.js library that provides a high-level API to control Chrome or Chromium over the DevTools Protocol. It's used for browser automation, navigation, and data extraction.
-   **Inquirer.js:** A collection of common interactive command-line user interfaces. Used for prompting the user for input (platform, URL, output path).
-   **Node.js `fs` Module:** Built-in module for interacting with the file system, used for reading cookie files and writing the generated HTML report.

### Key Features

-   **Stealth Mode:** Uses Puppeteer Stealth Plugin to avoid detection.
-   **User-Agent from File:** Reads your real browser User-Agent string from a file for maximum authenticity.
-   **Robust Auto-Scrolling:** Followers/following dialogs are auto-scrolled to the end to extract all users.
-   **Full Data Extraction:** Extracts all followers, following, posts, likers, commenters, and tagged posts.
-   **Login Check:** Verifies you are logged in before scraping.
-   **Interactive Prompts:** Guides the user through the scraping process. The output HTML report filename is always generated automatically using the user ID and username and saved in the directory you provide.
-   **Cookie-Based Authentication:** Utilizes provided cookie files to maintain a logged-in session, bypassing direct login within Puppeteer.
-   **Platform-Specific Scraping:**
    -   **Instagram:** Extracts numeric user ID, followers/following lists (all, via auto-scroll), and details for the latest 10 posts (caption, like count, likers, comment count, commenters, comments), and tagged posts.
    -   **Facebook:** Extracts numeric Facebook ID, friends list, and details for the latest 10 posts (like count, comment count, comments).
-   **HTML Report Generation:** Creates a single, well-structured HTML file with inline CSS for easy viewing of scraped data. Includes sections for profile info, connections (followers/following/friends), and posts. **The filename is always auto-generated.**
-   **Robust Selectors:** Employs specific and general CSS selectors with fallbacks to enhance reliability across potential website changes. Uses a compatible delay method instead of `page.waitForTimeout` for maximum Puppeteer compatibility.
-   **Progress Logging:** Provides console output to keep the user informed about the scraping process.

## Current Status

All core features for scraping and report generation have been implemented and refined. The project structure and documentation are complete and up-to-date. Dependency management is handled via `package.json` and `package-lock.json`.