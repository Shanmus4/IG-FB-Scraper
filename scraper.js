const puppeteer = require('puppeteer');
const fs = require('fs').promises;
const inquirer = require('inquirer');

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
            name: 'outputPath',
            message: 'Where do you want to save the HTML report?',
            validate: function (value) {
                if (value.length && value.endsWith('.html')) {
                    return true;
                } else {
                    return 'Please enter a valid file path with a .html extension.';
                }
            },
        },
    ];

    return inquirer.prompt(questions);
}

async function scrapeInstagram(page) {
    console.log('Scraping Instagram...');

    // Extract user ID
    const userId = await page.evaluate(() => {
        const match = document.cookie.match(/ds_user_id=([^;]+)/);
        return match ? match[1] : null;
    });

    // Extract followers and following
    const followers = await getFollows(page, 'followers');
    const following = await getFollows(page, 'following');

    // Extract posts
    const posts = await page.evaluate(() => {
        const postElements = document.querySelectorAll('article > div > div > div > div');
        const postData = [];
        for (let i = 0; i < Math.min(postElements.length, 10); i++) {
            const post = postElements[i];
            const caption = post.querySelector('h1')?.innerText || post.querySelector('div._a9zs > span')?.innerText;
            const likeCount = post.querySelector('span.xp7j5b_ > span')?.innerText || '0';
            const commentCount = post.querySelector('span.x1i64zmx > span')?.innerText || '0';
            const comments = Array.from(post.querySelectorAll('ul > li')).map(li => li.innerText);
            postData.push({ caption, likeCount, commentCount, comments });
        }
        return postData;
    });

    return { userId, followers, following, posts };
}

async function getFollows(page, type) {
    const link = await page.$(`a[href*="/${type}/"]`);
    if (!link) return [];

    await link.click();
    await page.waitForSelector('div[role="dialog"]');
    await page.waitForTimeout(2000); // Wait for dialog to load

    const list = [];
    const dialogSelector = 'div[role="dialog"]';

    let scrollCount = 0;
    while (list.length < 50 && scrollCount < 10) {
        const followers = await page.evaluate((selector) => {
            const dialog = document.querySelector(selector);
            if (!dialog) return [];
            const followersList = [];
            const followers = dialog.querySelectorAll('a[title]');
            followers.forEach(f => {
                if (!followersList.find(i => i.username === f.title)) {
                    followersList.push({ username: f.title, url: f.href });
                }
            });
            return followersList;
        }, dialogSelector);

        followers.forEach(f => {
            if (!list.find(i => i.username === f.username)) {
                list.push(f);
            }
        });

        await page.evaluate((selector) => {
            const dialog = document.querySelector(selector);
            if (dialog) dialog.scrollTop = dialog.scrollHeight;
        }, dialogSelector);

        await page.waitForTimeout(1000);
        scrollCount++;
    }

    // Close the dialog
    await page.keyboard.press('Escape');

    return list;
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
    const friendsLink = await page.$('a[href*="friends"] ') || await page.$('a[href*="/friends"] ');
    if (!friendsLink) return [];

    await friendsLink.click();
    await page.waitForSelector('a[data-gt]');
    await page.waitForTimeout(2000);

    const list = await page.evaluate(() => {
        const friendsList = [];
        const friendElements = document.querySelectorAll('a[data-gt]');
        friendElements.forEach(f => {
            friendsList.push({ username: f.innerText, url: f.href });
        });
        return friendsList;
    });

    return list;
}

async function generateReport(data, outputPath, platform) {
    let followersHtml = '';
    if (data.followers && data.followers.length > 0) {
        followersHtml = '<h2>Followers</h2><table><tr><th>Username</th><th>URL</th></tr>' +
            data.followers.map(f => `<tr><td>${f.username}</td><td><a href="${f.url}">${f.url}</a></td></tr>`).join('') + '</table>';
    }

    let followingHtml = '';
    if (data.following && data.following.length > 0) {
        followingHtml = '<h2>Following</h2><table><tr><th>Username</th><th>URL</th></tr>' +
            data.following.map(f => `<tr><td>${f.username}</td><td><a href="${f.url}">${f.url}</a></td></tr>`).join('') + '</table>';
    }

    let friendsHtml = '';
    if (data.friends && data.friends.length > 0) {
        friendsHtml = '<h2>Friends</h2><table><tr><th>Username</th><th>URL</th></tr>' +
            data.friends.map(f => `<tr><td>${f.username}</td><td><a href="${f.url}">${f.url}</a></td></tr>`).join('') + '</table>';
    }

    let postsHtml = '<h2>Posts</h2>' + data.posts.map(p => `
        <div class="post">
            <p><b>Caption:</b> ${p.caption}</p>
            <p><b>Likes:</b> ${p.likeCount || 'N/A'}</p>
            <p><b>Comments:</b> ${p.commentCount || 'N/A'}</p>
            <div><b>Comments:</b><ul>${p.comments.map(c => `<li>${c}</li>`).join('')}</ul></div>
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
                <h2>Profile Info</h2>
                <p><b>User ID:</b> ${data.userId}</p>
                ${platform === 'Instagram' ? followersHtml + followingHtml : friendsHtml}
                ${postsHtml}
            </body>
        </html>
    `;

    await fs.writeFile(outputPath, html);
    console.log(`Report saved to ${outputPath}`);
}

async function main() {
    const answers = await getQuestions();
    const { platform, profileUrl, outputPath } = answers;

    console.log('Starting scraper...');

    let cookies;
    try {
        cookies = await fs.readFile('cookies.txt', 'utf8');
    } catch (error) {
        console.error('Error reading cookies.txt:', error);
        return;
    }

    const browser = await puppeteer.launch({ headless: false });
    const page = await browser.newPage();

    await page.setExtraHTTPHeaders({
        'Cookie': cookies,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    });

    await page.goto(profileUrl, { waitUntil: 'networkidle2' });

    let scrapedData;
    if (platform === 'Instagram') {
        scrapedData = await scrapeInstagram(page);
    } else {
        scrapedData = await scrapeFacebook(page);
    }

    await generateReport(scrapedData, outputPath, platform);

    await browser.close();

    console.log('Scraping complete!');
}

main();