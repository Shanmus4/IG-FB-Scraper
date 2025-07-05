# Instagram & Facebook Scraper

This project provides a Node.js script utilizing Puppeteer to automate the scraping of public profile data from Instagram or Facebook. It allows users to extract information such as user IDs, follower/following/friends lists, and recent post details, generating a clean HTML report for easy viewing.

## Repository

[GitHub Repository Link](YOUR_GITHUB_REPO_LINK_HERE)

## Live Deployment

[Live Deployment Link](YOUR_LIVE_DEPLOYMENT_LINK_HERE)

## Local Setup Guide

To set up and run this project locally, follow these steps:

1.  **Clone the Repository:**
    ```bash
    git clone YOUR_GITHUB_REPO_LINK_HERE
    cd "IG FB Scraper"
    ```

2.  **Install Node.js:**
    Ensure you have Node.js installed on your system. You can download it from [nodejs.org](https://nodejs.org/).

3.  **Install Dependencies:**
    Navigate to the project's root directory in your terminal and install the required Node.js packages:
    ```bash
    npm init -y
    npm install puppeteer inquirer
    ```

4.  **Configure Cookies (`cookies.txt`):**
    This script relies on your authenticated browser session to scrape data. You need to provide your login cookies:
    -   Log in to Instagram or Facebook in your web browser.
    -   Open your browser's Developer Tools (usually by pressing `F12`).
    -   Go to the `Network` tab and refresh the page.
    -   Find any request to `instagram.com` or `facebook.com` (e.g., the main document request).
    -   In the `Headers` tab of that request, locate the `Cookie` request header.
    -   Copy the *entire* raw cookie string (the value of the `Cookie` header).
    -   Create a file named `cookies.txt` in the same directory as `scraper.js` and paste the copied cookie string into it.

## Commands to Run Locally

Once setup is complete, run the script from the project root:

```bash
node scraper.js
```

The script will then guide you through interactive prompts to select the platform, provide the profile URL, and specify the output HTML file path.

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
├── cookies.txt       # Stores user's raw cookie string for authentication
├── README.md         # Project documentation (this file)
├── PLANNING.md       # Project planning, goals, and technical details
└── TASKS.md          # Task log and progress tracking
├── package.json      # Node.js project metadata and dependencies
└── package-lock.json # Records the exact dependency tree
```

### Technologies Used

-   **Node.js:** JavaScript runtime environment.
-   **Puppeteer:** A Node.js library that provides a high-level API to control Chrome or Chromium over the DevTools Protocol. It's used for browser automation, navigation, and data extraction.
-   **Inquirer.js:** A collection of common interactive command-line user interfaces. Used for prompting the user for input (platform, URL, output path).
-   **Node.js `fs` Module:** Built-in module for interacting with the file system, used for reading `cookies.txt` and writing the generated HTML report.

### Key Features

-   **Interactive Prompts:** Guides the user through the scraping process.
-   **Cookie-Based Authentication:** Utilizes provided `cookies.txt` to maintain a logged-in session, bypassing direct login within Puppeteer.
-   **Platform-Specific Scraping:**
    -   **Instagram:** Extracts numeric user ID, followers/following lists (up to 50 entries), and details for the latest 10 posts (caption, like count, comment count, comments).
    -   **Facebook:** Extracts numeric Facebook ID, friends list, and details for the latest 10 posts (like count, comment count, comments).
-   **HTML Report Generation:** Creates a single, well-structured HTML file with inline CSS for easy viewing of scraped data. Includes sections for profile info, connections (followers/following/friends), and posts.
-   **Robust Selectors:** Employs specific and general CSS selectors with fallbacks to enhance reliability across potential website changes.
-   **Progress Logging:** Provides console output to keep the user informed about the scraping process.
