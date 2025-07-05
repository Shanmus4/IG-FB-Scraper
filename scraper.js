const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs').promises;
const inquirer = require('inquirer');
const path = require('path');

function randomDelay(min = 3000, max = 8000) {
    return new Promise(r => setTimeout(r, Math.floor(Math.random() * (max - min + 1)) + min));
}

async function getQuestions() {
    const questions = [
        {
            type: 'list',
            name: 'platform',
            message: 'Do you want to scrape Instagram or Facebook?',
            choices: ['Instagram', 'Facebook'],
        },
        {
            type: 'input',
            name: 'profileUrl',
            message: 'Paste the full profile link:',
            validate: function (value) {
                if (value.length) {
                    return true;
                } else {
                    return 'Please enter a profile link.';
                }
            },
        },
        {
            type: 'input',
            name: 'outputDir',
            message: 'Enter the directory where the HTML report should be saved:',
            validate: async function (value) {
                const fs = require('fs').promises;
                try {
                    const stat = await fs.stat(value);
                    if (stat.isDirectory()) {
                        return true;
                    } else {
                        return 'The path is not a directory.';
                    }
                } catch (e) {
                    return 'Directory does not exist. Please enter a valid directory path.';
                }
            },
        },
    ];

    return inquirer.prompt(questions);
}

async function scrapeInstagram(page, profileUrl) {
    console.log('Scraping Instagram...');

    // Extract profile info
    const profileInfo = await page.evaluate(() => {
        const username = document.querySelector('header a[href^="/"]')?.innerText || '';
        const fullName = document.querySelector('header h1, header h2')?.innerText || '';
        const bio = document.querySelector('header section > div > h1, header section > div > span, header section > div > div')?.innerText || '';
        const profilePic = document.querySelector('header img')?.src || '';
        const counts = Array.from(document.querySelectorAll('header li span'));
        const posts = counts[0]?.innerText || '';
        const followers = counts[1]?.innerText || '';
        const following = counts[2]?.innerText || '';
        return { username, fullName, bio, profilePic, posts, followers, following };
    });
    profileInfo.profileUrl = profileUrl;

    // Extract user ID
    const userId = await page.evaluate(() => {
        const match = document.cookie.match(/ds_user_id=([^;]+)/);
        return match ? match[1] : null;
    });

    // Extract followers and following
    const followers = await getFollows(page, 'followers');
    const following = await getFollows(page, 'following');

    // Extract post links from the profile grid
    const postLinks = await page.evaluate(() => {
        // Select all post links in the grid
        const anchors = Array.from(document.querySelectorAll('article a'));
        // Only keep links that look like post URLs
        return anchors.map(a => a.href).filter(href => /\/p\//.test(href)).slice(0, 10);
    });

    const posts = [];
    for (let i = 0; i < postLinks.length; i++) {
        try {
            await page.goto(postLinks[i], { waitUntil: 'networkidle2' });
            await page.waitForSelector('article');
            const postData = await page.evaluate(() => {
                const postLink = window.location.href;
                let caption = '';
                const captionElem = document.querySelector('div[role="presentation"] ul li div > div > div > span') || document.querySelector('h1');
                if (captionElem) caption = captionElem.innerText;
                // Likes dialog
                let likers = [];
                const likeButton = document.querySelector('section span[aria-label*="like"], section a[href$="/liked_by/"]');
                if (likeButton) likeButton.click();
                // Wait for likers dialog (if any)
                const likersDialog = document.querySelector('div[role="dialog"]');
                if (likersDialog) {
                    const likerAnchors = likersDialog.querySelectorAll('a[role="link"][tabindex="0"]');
                    likers = Array.from(likerAnchors).map(a => ({ username: a.textContent.trim(), url: 'https://instagram.com' + a.getAttribute('href') }));
                }
                // Comments
                const commentBlocks = Array.from(document.querySelectorAll('ul ul li'));
                const comments = commentBlocks.map(li => {
                    const userA = li.querySelector('a[role="link"][tabindex="0"]');
                    const username = userA ? userA.textContent.trim() : '';
                    const url = userA ? 'https://instagram.com' + userA.getAttribute('href') : '';
                    const text = li.querySelector('span')?.innerText || '';
                    return { username, url, text };
                });
                return { postLink, caption, likers, comments };
            });
            posts.push(postData);
            await randomDelay();
        } catch (err) {
            posts.push({ postLink: postLinks[i], caption: 'Error extracting post', likers: [], comments: [] });
        }
    }
    // Go back to profile page
    await page.goBack({ waitUntil: 'networkidle2' });
    await randomDelay();

    // Tagged posts
    let taggedPosts = [];
    try {
        // Click the tagged tab
        await page.evaluate(() => {
            const tabs = Array.from(document.querySelectorAll('a'));
            const taggedTab = tabs.find(a => a.getAttribute('href') && a.getAttribute('href').includes('/tagged/'));
            if (taggedTab) taggedTab.click();
        });
        await randomDelay();
        await page.waitForSelector('article a', { timeout: 10000 });
        const taggedLinks = await page.evaluate(() => {
            const anchors = Array.from(document.querySelectorAll('article a'));
            return anchors.map(a => a.href).filter(href => /\/p\//.test(href));
        });
        for (let i = 0; i < Math.min(taggedLinks.length, 10); i++) {
            try {
                await page.goto(taggedLinks[i], { waitUntil: 'networkidle2' });
                await randomDelay();
                await page.waitForSelector('article');
                const postData = await page.evaluate(() => {
                    const postLink = window.location.href;
                    let caption = '';
                    const captionElem = document.querySelector('div[role="presentation"] ul li div > div > div > span') || document.querySelector('h1');
                    if (captionElem) caption = captionElem.innerText;
                    // Likes dialog
                    let likers = [];
                    const likeButton = document.querySelector('section span[aria-label*="like"], section a[href$="/liked_by/"]');
                    if (likeButton) likeButton.click();
                    const likersDialog = document.querySelector('div[role="dialog"]');
                    if (likersDialog) {
                        const likerAnchors = likersDialog.querySelectorAll('a[role="link"][tabindex="0"]');
                        likers = Array.from(likerAnchors).map(a => ({ username: a.textContent.trim(), url: 'https://instagram.com' + a.getAttribute('href') }));
                    }
                    // Comments
                    const commentBlocks = Array.from(document.querySelectorAll('ul ul li'));
                    const comments = commentBlocks.map(li => {
                        const userA = li.querySelector('a[role="link"][tabindex="0"]');
                        const username = userA ? userA.textContent.trim() : '';
                        const url = userA ? 'https://instagram.com' + userA.getAttribute('href') : '';
                        const text = li.querySelector('span')?.innerText || '';
                        return { username, url, text };
                    });
                    return { postLink, caption, likers, comments };
                });
                taggedPosts.push(postData);
            } catch (err) {
                taggedPosts.push({ postLink: taggedLinks[i], caption: 'Error extracting post', likers: [], comments: [] });
            }
        }
    } catch (err) {
        // No tagged posts or failed to load
    }

    return { userId, followers, following, posts, taggedPosts, profileInfo };
}

async function getFollows(page, type) {
    const link = await page.$(`a[href*="/${type}/"]`);
    if (!link) return [];
    await link.click();
    await randomDelay();
    await page.waitForSelector('div[role="dialog"] a[role="link"][tabindex="0"]', { timeout: 60000 });
    await randomDelay();
    let allUsers = [];
    let lastCount = 0;
    let sameCountTries = 0;
    let maxTries = 50;
    let maxUsers = 10000;
    let reachedEnd = false;
    while (sameCountTries < maxTries && allUsers.length < maxUsers && !reachedEnd) {
        // Scroll the real scrollable container inside the dialog
        await page.evaluate(() => {
            const dialog = document.querySelector('div[role="dialog"]');
            if (!dialog) return;
            let scrollBox = dialog.querySelector('div[role="presentation"]');
            if (!scrollBox) {
                scrollBox = Array.from(dialog.querySelectorAll('div')).find(
                    d => d.scrollHeight > 1000 && (getComputedStyle(d).overflowY === 'auto' || getComputedStyle(d).overflowY === 'scroll')
                );
            }
            if (scrollBox) {
                scrollBox.scrollTop = scrollBox.scrollHeight;
            }
        });
        await randomDelay();
        const users = await page.evaluate(() => {
            const anchors = Array.from(document.querySelectorAll('div[role="dialog"] a[role="link"][tabindex="0"]'));
            return anchors
                .filter(a => a.href && a.getAttribute('href').startsWith('/') && a.textContent)
                .map(a => ({
                    username: a.textContent.trim(),
                    url: 'https://instagram.com' + a.getAttribute('href')
                }));
        });
        // Check if we've reached the end (scroll position doesn't change)
        const atEnd = await page.evaluate(() => {
            const dialog = document.querySelector('div[role="dialog"]');
            if (!dialog) return false;
            let scrollBox = dialog.querySelector('div[role="presentation"]');
            if (!scrollBox) {
                scrollBox = Array.from(dialog.querySelectorAll('div')).find(
                    d => d.scrollHeight > 1000 && (getComputedStyle(d).overflowY === 'auto' || getComputedStyle(d).overflowY === 'scroll')
                );
            }
            if (scrollBox) {
                return scrollBox.scrollTop + scrollBox.clientHeight >= scrollBox.scrollHeight;
            }
            return false;
        });
        if (users.length > lastCount) {
            lastCount = users.length;
            sameCountTries = 0;
            allUsers = users;
        } else {
            sameCountTries++;
        }
        if (atEnd) reachedEnd = true;
    }
    await page.keyboard.press('Escape');
    await randomDelay();
    return allUsers;
}

async function scrapeFacebook(page) {
    console.log('Scraping Facebook...');

    // Extract user ID
    const userId = await page.evaluate(() => {
        const match = document.body.innerHTML.match(/"entity_id":"(\d+)"/);
        return match ? match[1] : null;
    });

    // Extract friends
    const friends = await getFriends(page);

    // Extract posts
    const posts = await page.evaluate(() => {
        const postElements = document.querySelectorAll('div[data-ad-preview="message"]');
        const postData = [];
        for (let i = 0; i < Math.min(postElements.length, 10); i++) {
            const post = postElements[i];
            const caption = post.innerText || post.querySelector('div.xdj266r.x11i5r0o.x1k6rcq7.x1s688f.x1rqr2p4.x1jfb8zj.x1xmf6yo.x1e56ztr.x1x6prpr.x1iyjqo2.x2lwn1j.xeuugli.x18d9i69.x1mpkggp.x11xpdln.x1120s5i.x178xt8z.x1n2onr6.xh8yej3')?.innerText;
            const likeCount = post.parentElement.querySelector('span.x1e558r4')?.innerText || '0';
            const commentCount = post.parentElement.querySelector('div.x9f619.x1n2onr6.x1ja2u2z > div > div > div > a > span')?.innerText.split(' ')[0] || '0';
            const comments = Array.from(post.parentElement.querySelectorAll('div[aria-label="Comment"] div > div > span')).map(c => c.innerText);
            postData.push({ caption, likeCount, commentCount, comments });
        }
        return postData;
    });

    return { userId, friends, posts };
}

async function getFriends(page) {
    // Attempt to find the friends link. Facebook often uses 'friends' in the URL.
    const friendsLink = await page.$('a[href*="friends"] ') || await page.$('a[href*="/friends"] ');
    if (!friendsLink) return [];

    await friendsLink.click();
    // Wait for a common selector that appears on the friends list page.
    // This selector is also highly fragile and may need frequent updates.
    await page.waitForSelector('a[data-gt]');
    await randomDelay(); // Give some time for content to load

    const list = await page.evaluate(() => {
        const friendsList = [];
        // Selector for individual friend elements. 'a[data-gt]' is very generic
        // and will likely capture many non-friend links. A more specific selector
        // within the friends list container would be ideal but is prone to breaking.
        const friendElements = document.querySelectorAll('a[data-gt]');
        friendElements.forEach(f => {
            friendsList.push({ username: f.innerText, url: f.href });
        });
        return friendsList;
    });

    return list;
}

async function generateReport(data, outputPath, platform) {
    let profileHtml = '';
    if (data.profileInfo) {
        profileHtml = `<h2>Profile Info</h2>
            <img src="${data.profileInfo.profilePic}" alt="Profile Picture" style="width:100px;height:100px;border-radius:50%;"><br>
            <b>Username:</b> ${data.profileInfo.username}<br>
            <b>Full Name:</b> ${data.profileInfo.fullName}<br>
            <b>User ID:</b> ${data.userId}<br>
            <b>Instagram Link:</b> <a href="${data.profileInfo.profileUrl}">${data.profileInfo.profileUrl}</a><br>
            <b>Bio:</b> ${data.profileInfo.bio}<br>
            <b>Posts:</b> ${data.profileInfo.posts} | <b>Followers:</b> ${data.profileInfo.followers} | <b>Following:</b> ${data.profileInfo.following}<br><br>`;
    }

    let followersHtml = '';
    if (data.followers && data.followers.length > 0) {
        followersHtml = '<h2>Followers</h2><table><tr><th>Username</th><th>URL</th></tr>' +
            data.followers.map(f => `<tr><td><a href="${f.url}">${f.username}</a></td><td><a href="${f.url}">${f.url}</a></td></tr>`).join('') + '</table>';
    }

    let followingHtml = '';
    if (data.following && data.following.length > 0) {
        followingHtml = '<h2>Following</h2><table><tr><th>Username</th><th>URL</th></tr>' +
            data.following.map(f => `<tr><td><a href="${f.url}">${f.username}</a></td><td><a href="${f.url}">${f.url}</a></td></tr>`).join('') + '</table>';
    }

    let friendsHtml = '';
    if (data.friends && data.friends.length > 0) {
        friendsHtml = '<h2>Friends</h2><table><tr><th>Username</th><th>URL</th></tr>' +
            data.friends.map(f => `<tr><td>${f.username}</td><td><a href="${f.url}">${f.url}</a></td></tr>`).join('') + '</table>';
    }

    let postsHtml = '<h2>Posts</h2>' + (data.posts || []).map(p => `
        <div class="post">
            <p><b>Post Link:</b> <a href="${p.postLink}">${p.postLink}</a></p>
            <p><b>Caption:</b> ${p.caption}</p>
            <p><b>Liked by:</b> ${p.likers && p.likers.length > 0 ? p.likers.map(l => `<a href="${l.url}">${l.username}</a>`).join(', ') : 'N/A'}</p>
            <p><b>Comments:</b></p>
            <ul>${p.comments && p.comments.length > 0 ? p.comments.map(c => `<li><a href="${c.url}">${c.username}</a>: ${c.text}</li>`).join('') : '<li>N/A</li>'}</ul>
        </div>
    `).join('');

    let taggedHtml = '<h2>Tagged Posts</h2>' + (data.taggedPosts || []).map(p => `
        <div class="post">
            <p><b>Post Link:</b> <a href="${p.postLink}">${p.postLink}</a></p>
            <p><b>Caption:</b> ${p.caption}</p>
            <p><b>Liked by:</b> ${p.likers && p.likers.length > 0 ? p.likers.map(l => `<a href="${l.url}">${l.username}</a>`).join(', ') : 'N/A'}</p>
            <p><b>Comments:</b></p>
            <ul>${p.comments && p.comments.length > 0 ? p.comments.map(c => `<li><a href="${c.url}">${c.username}</a>: ${c.text}</li>`).join('') : '<li>N/A</li>'}</ul>
        </div>
    `).join('');

    const html = `
        <html>
            <head>
                <title>${platform} Profile Report</title>
                <style>
                    body { font-family: sans-serif; }
                    table { border-collapse: collapse; width: 100%; }
                    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                    .post { border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; }
                </style>
            </head>
            <body>
                <h1>${platform} Profile Report</h1>
                ${profileHtml}
                ${platform === 'Instagram' ? followersHtml + followingHtml : friendsHtml}
                ${postsHtml}
                ${taggedHtml}
            </body>
        </html>
    `;

    await fs.writeFile(outputPath, html);
    console.log(`Report saved to ${outputPath}`);
}

async function main() {
    const answers = await getQuestions();
    const { platform, profileUrl, outputDir } = answers;

    console.log('Starting scraper...');

    let cookiesRaw;
    let cookieFileName = '';
    let userAgentFile = '';

    if (platform === 'Instagram') {
        cookieFileName = 'instagram_cookies.txt';
        userAgentFile = 'instagram_useragent.txt';
    } else if (platform === 'Facebook') {
        cookieFileName = 'facebook_cookies.txt';
        userAgentFile = 'facebook_useragent.txt';
    }

    try {
        cookiesRaw = await fs.readFile(cookieFileName, 'utf8');
    } catch (error) {
        console.error(`Error reading ${cookieFileName}:`, error);
        console.error(`Please make sure you have created a file named ${cookieFileName} in the same directory as scraper.js and pasted your raw cookie string into it.`);
        return;
    }

    let userAgent;
    try {
        userAgent = await fs.readFile(userAgentFile, 'utf8');
        userAgent = userAgent.trim();
    } catch (error) {
        console.error(`Error reading ${userAgentFile}:`, error);
        console.error(`Please make sure you have created a file named ${userAgentFile} in the same directory as scraper.js and pasted your real User-Agent string into it.`);
        return;
    }

    const browser = await puppeteer.launch({ headless: false });
    const page = await browser.newPage();

    // Set viewport, language, and timezone to match a real browser
    await page.setViewport({ width: 1200, height: 800, deviceScaleFactor: 1 });
    await page.emulateTimezone('America/New_York'); // Change to your real timezone if needed
    await page.setExtraHTTPHeaders({
        'Accept-Language': 'en-US,en;q=0.9',
        'User-Agent': userAgent,
    });

    // Always parse cookies as header string
    const cookies = cookiesRaw.split(';').map(pair => {
        const [name, ...rest] = pair.trim().split('=');
        return { name, value: rest.join('='), domain: '.instagram.com', path: '/' };
    });
    await page.setCookie(...cookies);
    await randomDelay();

    await page.goto(profileUrl, { waitUntil: 'networkidle2' });
    await randomDelay();

    // Check login status (look for profile icon or main content)
    const loggedIn = await page.evaluate(() => {
        return !!document.querySelector('nav img[alt*="profile"]') || !!document.querySelector('header');
    });
    if (!loggedIn) {
        console.error('Login check failed: You are not logged in. Please check your cookies and User-Agent.');
        await browser.close();
        return;
    }

    let scrapedData;
    if (platform === 'Instagram') {
        scrapedData = await scrapeInstagram(page, profileUrl);
    } else {
        scrapedData = await scrapeFacebook(page);
    }

    // Save as UID_Instagram_Username.html or UID_Facebook_Username.html
    let userId = scrapedData.userId || 'profile';
    let username = scrapedData.profileInfo?.username || scrapedData.profileInfo?.name || 'user';
    let platformLabel = platform === 'Instagram' ? 'Instagram' : 'Facebook';
    let finalOutputPath = path.join(outputDir, `${userId}_${platformLabel}_${username}.html`);

    await generateReport(scrapedData, finalOutputPath, platform);

    await browser.close();

    console.log('Scraping complete!');
}

main();