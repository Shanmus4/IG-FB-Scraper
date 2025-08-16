import os
import time
import json
import re
import csv
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs
from webdriver_manager.chrome import ChromeDriverManager

# Import the HTML builder
from facebook_html_builder import FacebookHTMLBuilder

class FacebookScraper:
    def __init__(self):
        self.browser = None
        self.cookies = []
        self.load_cookies()
        self.setup_browser()
        self._add_cookies()

    def load_cookies(self):
        """Load Facebook cookies from .env file."""
        try:
            if not os.path.exists('.env'):
                raise FileNotFoundError("No .env file found")
                
            with open('.env', 'r', encoding='utf-8') as f:
                cookie_lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                
            if not cookie_lines:
                raise ValueError("No cookies found in .env file")
                
            self.cookies = []
            for line in cookie_lines:
                if 'facebook.com' in line:
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        self.cookies.append({
                            'domain': parts[0].lstrip('.').lstrip('.'),
                            'name': parts[5],
                            'value': parts[6],
                            'path': parts[2],
                            'secure': parts[3].upper() == 'TRUE',
                            'httpOnly': False
                        })
            
            if not self.cookies:
                raise ValueError("No valid Facebook cookies found in .env")
                
        except Exception as e:
            print("[!] Error loading cookies:", e)
            print("\nPlease follow these steps to get your cookies:")
            print("1. Log in to Facebook in Chrome")
            print("2. Open Developer Tools (F12)")
            print("3. Go to Application > Storage > Cookies > https://www.facebook.com")
            print("4. Right-click and select 'Copy All as Netscape cookie file'")
            print("5. Paste the contents into the .env file")
            raise

    def setup_browser(self):
        """Setup Chrome browser with options."""
        chrome_options = Options()
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("start-maximized")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 1
        })
        
        try:
            # Use webdriver_manager to handle ChromeDriver
            self.browser = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
            self.browser.implicitly_wait(10)
        except Exception as e:
            print("[!] Error setting up browser:", e)
            raise


    def _extract_post_text(self, item):
        """Extract post text from HTML element."""
        actual_posts = item.find_all(attrs={"data-testid": "post_message"})
        text = ""
        if actual_posts:
            for post in actual_posts:
                paragraphs = post.find_all('p')
                for paragraph in paragraphs:
                    text += paragraph.get_text() + "\n"
        return text.strip()


def _extract_link(item):
    postLinks = item.find_all(class_="_6ks")
    link = ""
    for postLink in postLinks:
        link = postLink.find('a').get('href')
    return link


def _extract_post_id(item):
    postIds = item.find_all(class_="_5pcq")
    post_id = ""
    for postId in postIds:
        post_id = f"https://www.facebook.com{postId.get('href')}"
    return post_id


def _extract_image(item):
    postPictures = item.find_all(class_="scaledImageFitWidth img")
    image = ""
    for postPicture in postPictures:
        image = postPicture.get('src')
    return image


def _extract_shares(item):
    postShares = item.find_all(class_="_4vn1")
    shares = ""
    for postShare in postShares:

        x = postShare.string
        if x is not None:
            x = x.split(">", 1)
            shares = x
        else:
            shares = "0"
    return shares


def _extract_comments(item):
    postComments = item.findAll("div", {"class": "_4eek"})
    comments = dict()
    # print(postDict)
    for comment in postComments:
        if comment.find(class_="_6qw4") is None:
            continue

        commenter = comment.find(class_="_6qw4").text
        comments[commenter] = dict()

        comment_text = comment.find("span", class_="_3l3x")

        if comment_text is not None:
            comments[commenter]["text"] = comment_text.text

        comment_link = comment.find(class_="_ns_")
        if comment_link is not None:
            comments[commenter]["link"] = comment_link.get("href")

        comment_pic = comment.find(class_="_2txe")
        if comment_pic is not None:
            comments[commenter]["image"] = comment_pic.find(class_="img").get("src")

        commentList = item.find('ul', {'class': '_7791'})
        if commentList:
            comments = dict()
            comment = commentList.find_all('li')
            if comment:
                for litag in comment:
                    aria = litag.find("div", {"class": "_4eek"})
                    if aria:
                        commenter = aria.find(class_="_6qw4").text
                        comments[commenter] = dict()
                        comment_text = litag.find("span", class_="_3l3x")
                        if comment_text:
                            comments[commenter]["text"] = comment_text.text
                            # print(str(litag)+"\n")

                        comment_link = litag.find(class_="_ns_")
                        if comment_link is not None:
                            comments[commenter]["link"] = comment_link.get("href")

                        comment_pic = litag.find(class_="_2txe")
                        if comment_pic is not None:
                            comments[commenter]["image"] = comment_pic.find(class_="img").get("src")

                        repliesList = litag.find(class_="_2h2j")
                        if repliesList:
                            reply = repliesList.find_all('li')
                            if reply:
                                comments[commenter]['reply'] = dict()
                                for litag2 in reply:
                                    aria2 = litag2.find("div", {"class": "_4efk"})
                                    if aria2:
                                        replier = aria2.find(class_="_6qw4").text
                                        if replier:
                                            comments[commenter]['reply'][replier] = dict()

                                            reply_text = litag2.find("span", class_="_3l3x")
                                            if reply_text:
                                                comments[commenter]['reply'][replier][
                                                    "reply_text"] = reply_text.text

                                            r_link = litag2.find(class_="_ns_")
                                            if r_link is not None:
                                                comments[commenter]['reply']["link"] = r_link.get("href")

                                            r_pic = litag2.find(class_="_2txe")
                                            if r_pic is not None:
                                                comments[commenter]['reply']["image"] = r_pic.find(
                                                    class_="img").get("src")
    return comments


def _extract_reaction(item):
    toolBar = item.find_all(attrs={"role": "toolbar"})

    if not toolBar:  # pretty fun
        return
    reaction = dict()
    for toolBar_child in toolBar[0].children:
        str = toolBar_child['data-testid']
        reaction = str.split("UFI2TopReactions/tooltip_")[1]

        reaction[reaction] = 0

        for toolBar_child_child in toolBar_child.children:

            num = toolBar_child_child['aria-label'].split()[0]

            # fix weird ',' happening in some reaction values
            num = num.replace(',', '.')

            if 'K' in num:
                realNum = float(num[:-1]) * 1000
            else:
                realNum = float(num)

            reaction[reaction] = realNum
    return reaction


def _extract_html(bs_data):

    #Add to check
    with open('./bs.html',"w", encoding="utf-8") as file:
        file.write(str(bs_data.prettify()))

    k = bs_data.find_all(class_="_5pcr userContentWrapper")
    postBigDict = list()

    for item in k:
        postDict = dict()
        postDict['Post'] = _extract_post_text(item)
        postDict['Link'] = _extract_link(item)
        postDict['PostId'] = _extract_post_id(item)
        postDict['Image'] = _extract_image(item)
        postDict['Shares'] = _extract_shares(item)
        postDict['Comments'] = _extract_comments(item)
        # postDict['Reaction'] = _extract_reaction(item)

        #Add to check
        postBigDict.append(postDict)
        with open('./postBigDict.json','w', encoding='utf-8') as file:
            file.write(json.dumps(postBigDict, ensure_ascii=False).encode('utf-8').decode())

    return postBigDict


def _login(browser, email, password):
    browser.get("http://facebook.com")
    browser.maximize_window()
    browser.find_element_by_name("email").send_keys(email)
    browser.find_element_by_name("pass").send_keys(password)
    browser.find_element_by_id('loginbutton').click()
    time.sleep(5)


def _count_needed_scrolls(browser, infinite_scroll, numOfPost):
    if infinite_scroll:
        lenOfPage = browser.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);var lenOfPage=document.body.scrollHeight;return lenOfPage;"
        )
    else:
        # roughly 8 post per scroll kindaOf
        lenOfPage = int(numOfPost / 8)
    print("Number Of Scrolls Needed " + str(lenOfPage))
    return lenOfPage


def _scroll(browser, infinite_scroll, lenOfPage):
    lastCount = -1
    match = False

    while not match:
        if infinite_scroll:
            lastCount = lenOfPage
        else:
            lastCount += 1

        # wait for the browser to load, this time can be changed slightly ~3 seconds with no difference, but 5 seems
        # to be stable enough
        time.sleep(5)

        if infinite_scroll:
            lenOfPage = browser.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);var lenOfPage=document.body.scrollHeight;return "
                "lenOfPage;")
        else:
            browser.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);var lenOfPage=document.body.scrollHeight;return "
                "lenOfPage;")

        if lastCount == lenOfPage:
            match = True


    def run(self, username):
        """
        Run the Facebook scraper with interactive prompts.
        
        Args:
            username (str): Facebook username or profile URL
            
        Returns:
            str: Path to the generated HTML report
        """
        try:
            # Add cookies and verify session
            self._add_cookies()
            
            # Navigate to profile
            if not username.startswith('http'):
                username = f'https://www.facebook.com/{username}'
                
            print(f"[i] Navigating to {username}")
            self.browser.get(username)
            
            # Scroll to load posts (scrape all available)
            print("[i] Loading posts (this may take a while)...")
            self._scroll_to_load_posts(1000)  # Large number to get all posts
            
            # Extract data
            print("[i] Extracting profile data...")
            soup = bs(self.browser.page_source, 'html.parser')
            
            # Extract profile info
            profile_name = self._extract_profile_name(soup)
            
            print("[i] Extracting posts...")
            posts = self._extract_posts(soup, 1000, True)  # Get all posts with comments
            
            # Generate profile data
            print("[i] Generating report...")
            profile_data = {
                'name': profile_name or username.split('/')[-1],
                'profile_picture': self._extract_profile_picture(soup),
                'follower_count': self._extract_follower_count(soup),
                'following_count': 0,  # Facebook doesn't show this publicly
                'about': self._extract_about(soup),
                'posts': posts
            }
            
            # Generate HTML report
            print("[i] Generating HTML report...")
            builder = FacebookHTMLBuilder(username.split('/')[-1], profile_data)
            output_path = builder.save_html()
            
            print(f"\n[i] HTML report generated: {os.path.abspath(output_path)}")
            return output_path
            
        except Exception as e:
            print(f"[!] Error: {str(e)}")
            raise
        finally:
            if self.browser:
                self.browser.quit()

    # click on all the comments to scrape them all!
    # TODO: need to add more support for additional second level comments
    # TODO: ie. comment of a comment

    if scrape_comment:
        #first uncollapse collapsed comments
        unCollapseCommentsButtonsXPath = '//a[contains(@class,"_666h")]'
        unCollapseCommentsButtons = browser.find_elements_by_xpath(unCollapseCommentsButtonsXPath)
        for unCollapseComment in unCollapseCommentsButtons:
            action = webdriver.common.action_chains.ActionChains(browser)
            try:
                # move to where the un collapse on is
                action.move_to_element_with_offset(unCollapseComment, 5, 5)
                action.perform()
                unCollapseComment.click()
            except:
                # do nothing right here
                pass

        #second set comment ranking to show all comments
        rankDropdowns = browser.find_elements_by_class_name('_2pln') #select boxes who have rank dropdowns
        rankXPath = '//div[contains(concat(" ", @class, " "), "uiContextualLayerPositioner") and not(contains(concat(" ", @class, " "), "hidden_elem"))]//div/ul/li/a[@class="_54nc"]/span/span/div[@data-ordering="RANKED_UNFILTERED"]'
        for rankDropdown in rankDropdowns:
            #click to open the filter modal
            action = webdriver.common.action_chains.ActionChains(browser)
            try:
                action.move_to_element_with_offset(rankDropdown, 5, 5)
                action.perform()
                rankDropdown.click()
            except:
                pass

            # if modal is opened filter comments
            ranked_unfiltered = browser.find_elements_by_xpath(rankXPath) # RANKED_UNFILTERED => (All Comments)
            if len(ranked_unfiltered) > 0:
                try:
                    ranked_unfiltered[0].click()
                except:
                    pass    
        
        moreComments = browser.find_elements_by_xpath('//a[@class="_4sxc _42ft"]')
        print("Scrolling through to click on more comments")
        while len(moreComments) != 0:
            for moreComment in moreComments:
                action = webdriver.common.action_chains.ActionChains(browser)
                try:
                    # move to where the comment button is
                    action.move_to_element_with_offset(moreComment, 5, 5)
                    action.perform()
                    moreComment.click()
                except:
                    # do nothing right here
                    pass

            moreComments = browser.find_elements_by_xpath('//a[@class="_4sxc _42ft"]')

    # Now that the page is fully scrolled, grab the source code.
    source_data = browser.page_source

    # Throw your source into BeautifulSoup and start parsing!
    bs_data = bs(source_data, 'html.parser')

    postBigDict = _extract_html(bs_data)
    browser.close()
    
    # Generate HTML report
    if postBigDict:
        profile_data = {
            'name': 'Facebook Profile',  # Could be extracted from page if needed
            'profile_picture': '',  # Could be extracted from page if needed
            'follower_count': 0,  # Could be extracted from page if needed
            'following_count': 0,  # Could be extracted from page if needed
            'about': '',  # Could be extracted from page if needed
            'posts': postBigDict
        }
        
        # Get username from URL or use a default
        username = 'facebook_profile'
        if '/' in args.page.rstrip('/'):
            pass  # TODO: Add logic if needed, or remove if unnecessary

    def _add_cookies(self):
        """Add cookies to the browser session."""
        print("[i] Setting up session with cookies...")
        self.browser.get("https://www.facebook.com")
        
        # Clear existing cookies
        self.browser.delete_all_cookies()
        
        # Add each cookie
        for cookie in self.cookies:
            try:
                self.browser.add_cookie(cookie)
            except Exception as e:
                print(f"[!] Warning: Could not add cookie {cookie.get('name')}")
        
        # Refresh to apply cookies
        self.browser.refresh()
        time.sleep(2)
        
        # Verify login
        if "login" in self.browser.current_url:
            raise Exception("Failed to authenticate with provided cookies. They may be invalid or expired.")

    def _scroll_to_load_posts(self, num_posts):
        """Scroll the page to load more posts."""
        last_height = self.browser.execute_script("return document.body.scrollHeight")
        posts_loaded = 0
        
        while posts_loaded < num_posts:
            # Scroll down
            self.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for content to load
            
            # Check if we've reached the bottom
            new_height = self.browser.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
                
            last_height = new_height
            
            # Count loaded posts
            posts = self.browser.find_elements(By.XPATH, "//div[@role='article']")
            posts_loaded = len(posts)
            
            print(f"\r[i] Loaded {posts_loaded} posts...", end="")
            
            if posts_loaded >= num_posts:
                break
                
        print()

    def _extract_profile_name(self, soup):
        """Extract the profile name from the page."""
        try:
            name_element = soup.find('h1', {'class': 'x1heor9g'})  # Update class if needed
            return name_element.text.strip() if name_element else None
        except:
            return None

    def _extract_profile_picture(self, soup):
        """Extract the profile picture URL."""
        try:
            img = soup.find('img', {'class': 'x1ey2m1c'})  # Update class if needed
            return img.get('src') if img else ''
        except:
            return ''

    def _extract_follower_count(self, soup):
        """Extract the follower count."""
        try:
            # This is a placeholder - Facebook's structure may require adjustment
            followers = soup.find('div', text=lambda x: x and 'followers' in x.lower())
            if followers:
                return int(''.join(filter(str.isdigit, followers.text)))
            return 0
        except:
            return 0

    def _extract_about(self, soup):
        """Extract the about section."""
        try:
            about_section = soup.find('div', {'class': 'x1y332bk'})  # Update class if needed
            return about_section.text.strip() if about_section else ''
        except:
            return ''

    def _extract_posts(self, soup, num_posts, scrape_comments=False):
        """Extract posts from the page."""
        posts = []
        post_elements = soup.find_all('div', {'role': 'article'})
        
        for i, post in enumerate(post_elements[:num_posts], 1):
            print(f"\r[i] Processing post {i}/{min(len(post_elements), num_posts)}...", end="")
            
            post_data = {
                'Post': self._extract_post_text(post),
                'Link': self._extract_link(post),
                'Image': self._extract_image(post),
                'Shares': self._extract_shares(post),
                'Comments': {}
            }
            
            if scrape_comments:
                post_data['Comments'] = self._extract_comments(post)
                
            posts.append(post_data)
            
        print()
        return posts

def main():
    print("\n" + "="*50)
    print("FACEBOOK PROFILE SCRAPER".center(50))
    print("="*50)
    
    # Get username
    username = input("\nEnter Facebook username or profile URL: ").strip()
    
    print("\n[i] Starting Facebook scraper...")
    
    try:
        scraper = FacebookScraper()
        output_file = scraper.run(username)
        
        print("\n" + "="*50)
        print(f"[✓] Scraping complete!")
        print(f"[i] Report saved to: {os.path.abspath(output_file)}")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"\n[!] Error: {str(e)}")
        exit(1)
    except KeyboardInterrupt:
        print("\n[!] Scraping interrupted by user")
        exit(1)

if __name__ == "__main__":
    main()