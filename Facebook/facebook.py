#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook mbasic scraper (cookie login, no API).
- Reads raw cookie string from .env (one line, no KEY=VALUE, just the cookie header).
- Asks for a profile URL (www/m/mbasic allowed). Converts to mbasic internally.
- Scrapes:
  * Profile header (name, slug, profile pic embedded Base64)
  * Intro/Bio (best-effort)
  * About pages (work, education, places, family/relationships/contact if present)
  * Friends list (names + profile links)
  * Photos uploaded by the user ("Photos by") and tagged ("Photos of")
  * For each photo post:
      - Caption (best-effort)
      - Main image (embedded Base64; tries full-size first)
      - Reactions (list of users with profile links)
      - Comments (user + link + text, heuristic)
- Outputs a neat HTML report with collapsible sections.

Requires:
  selenium==4.21.0
  beautifulsoup4==4.12.3
  lxml==5.2.2
  requests==2.32.3
  python-dotenv==1.0.1
"""

import os
import re
import time
import base64
import random
import html
import json
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional

import requests
from bs4 import BeautifulSoup as BS
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ------------- Config -------------
HEADLESS = False  # set to True if you want headless Chrome
SLEEP_MIN, SLEEP_MAX = 0.8, 1.7

MAX_FRIENDS = 300
MAX_PHOTOS_BY = 60
MAX_PHOTOS_OF = 60
MAX_REACTIONS = 10000
MAX_COMMENTS = 10000

REQUESTS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ------------- Helpers -------------
def rs():
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

def read_raw_cookie_from_env(env_path: str) -> str:
    """Read first non-empty non-comment line from .env as the raw cookie string."""
    load_dotenv(env_path)
    # Try entire file raw (exactly like your IG script supports)
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Strip surrounding quotes if present
                if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
                    line = line[1:-1]
                return line
    except Exception:
        pass
    # As a fallback, allow INSTAGRAM-style key (not required)
    val = os.getenv("FACEBOOK_COOKIE") or os.getenv("COOKIE_STRING")
    if val:
        return val.strip().strip('"').strip("'")
    raise RuntimeError("Cookie not found. Put your raw cookie string in .env (single line, no KEY=VALUE).")

def split_cookie_pairs(raw: str) -> List[Tuple[str, str]]:
    out = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        out.append((name.strip(), value.strip()))
    return out

def ensure_mbasic(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc.replace("www.", "mbasic.", 1)
    elif netloc.startswith("m."):
        netloc = netloc.replace("m.", "mbasic.", 1)
    elif not netloc.startswith("mbasic."):
        # assume profile slug pasted without domain
        return "https://mbasic.facebook.com/" + url.lstrip("/")
    rebuilt = parsed._replace(netloc=netloc)
    # strip extra query tracking for stability
    return rebuilt.geturl()

def urljoin(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)

def abs_mbasic(href: str) -> str:
    if href.startswith("http"):
        return href
    return "https://mbasic.facebook.com" + (href if href.startswith("/") else "/" + href)

def make_requests_session(raw_cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": REQUESTS_UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://mbasic.facebook.com/",
        "Origin": "https://mbasic.facebook.com",
        "Cookie": raw_cookie
    })
    return s

def download_b64(session: requests.Session, url: str) -> str:
    try:
        r = session.get(url, timeout=30, allow_redirects=True, stream=True)
        if r.status_code != 200:
            return ""
        ct = r.headers.get("content-type", "image/jpeg")
        data = r.content
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{ct};base64,{b64}"
    except Exception:
        return ""

def soup(html_text: str) -> BS:
    return BS(html_text, "lxml")

def wait_for(driver, by, sel, t=10):
    return WebDriverWait(driver, t).until(EC.presence_of_element_located((by, sel)))

def try_find_text_link(driver, texts: List[str]) -> Optional[str]:
    anchors = driver.find_elements(By.TAG_NAME, "a")
    for a in anchors:
        t = (a.text or "").strip().lower()
        if not t:
            continue
        for want in texts:
            if want in t:
                href = a.get_attribute("href") or ""
                if href:
                    return href
    return None

# ------------- Selenium boot + cookie login -------------
def build_driver(headless: bool) -> webdriver.Chrome:
    opts = Options()
    if headless:
        # New headless mode
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--start-maximized")
    # more stable
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    # UA: let Chrome use its native UA; requests uses its own
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(45)
    return driver

def login_with_raw_cookie(driver: webdriver.Chrome, raw_cookie: str):
    # Must visit domain first
    driver.get("https://mbasic.facebook.com/")
    rs()
    # Use CDP to set cookies (works for HttpOnly)
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        pairs = split_cookie_pairs(raw_cookie)
        for name, value in pairs:
            try:
                driver.execute_cdp_cmd("Network.setCookie", {
                    "name": name,
                    "value": value,
                    "domain": ".facebook.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": False,  # fb will promote flags as needed
                    "sameSite": "None",
                    "url": "https://mbasic.facebook.com/"
                })
            except Exception:
                # Fallback to Selenium add_cookie
                try:
                    driver.add_cookie({"name": name, "value": value, "domain": ".facebook.com", "path": "/"})
                except Exception:
                    pass
        driver.get("https://mbasic.facebook.com/")
        rs()
    except WebDriverException:
        pass

# ------------- Extractors -------------
def get_profile_header(driver, req_sess: requests.Session, profile_url: str) -> Dict[str, Any]:
    driver.get(profile_url)
    rs()
    page = driver.page_source
    doc = soup(page)

    # Name: title or h3 near profile
    name = ""
    t = doc.find("title")
    if t and t.text:
        name = t.text.strip()

    # Slug from URL
    parsed = urllib.parse.urlparse(profile_url)
    slug = parsed.path.strip("/")

    # Profile pic: try common patterns
    # 1) link "View Profile Picture" then inside img
    # 2) any img with scontent near top
    ppic_b64 = ""
    img_url = ""
    # try: an <a> that contains text like 'View Profile Picture' or '/photo.php'
    a_candidates = doc.select("a[href*='photo.php']")
    for a in a_candidates:
        img = a.find("img")
        if img and img.get("src", "").find("scontent") != -1:
            img_url = img["src"]
            break
    if not img_url:
        img = doc.find("img", src=re.compile(r"scontent"))
        if img:
            img_url = img.get("src", "")
    if img_url:
        ppic_b64 = download_b64(req_sess, img_url)

    # Intro/Bio: On mbasic, often a small “Intro” box with lines
    intro_texts = []
    # Try to locate a block near a link with 'Intro' text
    intro_anchor = doc.find("a", string=re.compile(r"intro", re.I))
    if intro_anchor:
        # collect sibling divs
        container = intro_anchor.find_parent("div")
        if container:
            for d in container.find_all("div"):
                t = d.get_text(" ", strip=True)
                if t and "Intro" not in t:
                    intro_texts.append(t)
    # also scan small blocks with icons
    for d in doc.select("div"):
        txt = d.get_text(" ", strip=True)
        if txt and len(txt) < 300 and "Intro" not in txt:
            if any(k in txt.lower() for k in ["works at", "studied", "lives in", "from", "single", "married"]):
                intro_texts.append(txt)

    return {
        "name": name,
        "slug": slug,
        "profile_pic_b64": ppic_b64,
        "intro": list(dict.fromkeys(intro_texts)),  # de-dup preserve order
    }

def scrape_about_sections(driver, base_profile_url: str) -> Dict[str, List[str]]:
    """
    Tries several About subpages and collects bullet lines.
    """
    out: Dict[str, List[str]] = {}
    base = base_profile_url.rstrip("/")
    candidates = [
        "/about",
        "/about?view=education",
        "/about?view=work",
        "/about?view=contact_basic",
        "/about?view=relationship",
        "/about?view=places",
        "/about?view=family",
        "/about?section=overview",
        "/about?section=education",
        "/about?section=work",
        "/about?section=places",
        "/about?section=contact-info",
        "/about?section=relationship",
        "/about?section=family",
    ]
    seen_urls = set()
    for tail in candidates:
        u = abs_mbasic(base + tail if not base.endswith("/about") else base + tail.replace("/about", ""))
        if u in seen_urls:
            continue
        seen_urls.add(u)
        try:
            driver.get(u)
            rs()
            doc = soup(driver.page_source)
            # section name: h3 or title
            heading = ""
            h3 = doc.find("h3")
            if h3 and h3.text:
                heading = h3.text.strip()
            if not heading:
                t = doc.find("title")
                if t and t.text:
                    heading = t.text.strip()
            items: List[str] = []
            # collect list-like lines
            for li in doc.select("li"):
                txt = li.get_text(" ", strip=True)
                if txt and len(txt) < 400:
                    items.append(txt)
            # also div bullets
            if len(items) < 3:
                for d in doc.select("div"):
                    txt = d.get_text(" ", strip=True)
                    if txt and 4 < len(txt) < 400 and any(k in txt.lower() for k in ["works", "studied", "lives", "from", "relationship", "married", "single", "family", "city", "phone", "email"]):
                        items.append(txt)
            items = list(dict.fromkeys(items))
            if heading and items:
                out.setdefault(heading, []).extend(items)
        except Exception:
            continue
    return out

def scrape_friends(driver, base_profile_url: str, limit=MAX_FRIENDS) -> List[Dict[str, str]]:
    """
    Visits /friends and paginates by "See more friends" links.
    """
    results = []
    visited = set()

    # find friends link
    driver.get(base_profile_url)
    rs()
    href = try_find_text_link(driver, ["friends", "friend"])
    if not href:
        # fallback direct
        href = abs_mbasic(base_profile_url.rstrip("/") + "/friends")

    # paginate
    next_url = href if href.startswith("http") else abs_mbasic(href)
    while next_url and len(results) < limit:
        driver.get(next_url)
        rs()
        html_src = driver.page_source
        doc = soup(html_src)
        # friends are anchors with profile links + image or name
        for a in doc.select("a"):
            name = (a.text or "").strip()
            href = a.get("href") or ""
            if not name or not href:
                continue
            # profile links: /profile.php?id=... or /{slug}
            if re.search(r"^/(profile\.php\?id=\d+|[A-Za-z0-9\.\-_]+)(/)?(\?|$)", href):
                full = abs_mbasic(href)
                key = (name, full)
                if key not in visited:
                    visited.add(key)
                    results.append({"name": name, "url": full})
                    if len(results) >= limit:
                        break
        if len(results) >= limit:
            break
        # find "See more" pagination
        nxt = None
        for a in doc.select("a"):
            t = (a.text or "").strip().lower()
            if t in ("see more friends", "see more", "see all friends", "more friends"):
                href = a.get("href") or ""
                if href:
                    nxt = abs_mbasic(href)
                    break
        next_url = nxt
    return results

def collect_photo_links(driver, profile_url: str, which: str, limit: int) -> List[str]:
    """
    which: 'by' or 'of'
    Tries to reach Photos tab, then 'Photos by' or 'Photos of', and paginates collecting photo.php?fbid links.
    """
    assert which in ("by", "of")
    base = profile_url.rstrip("/")
    driver.get(base)
    rs()

    # Find "Photos" link from profile
    photos_link = try_find_text_link(driver, ["photos", "photo"])
    if not photos_link:
        # fallback direct
        photos_link = abs_mbasic(base + "/photos")

    # Open photos hub
    driver.get(photos_link if photos_link.startswith("http") else abs_mbasic(photos_link))
    rs()
    hub_html = soup(driver.page_source)

    # Find "See all" for the right section
    target_link = None
    for a in hub_html.select("a"):
        t = (a.text or "").strip().lower()
        href = a.get("href") or ""
        if which == "by" and ("your photos" in t or "uploads" in t or "photos" in t):
            # Prefer an href that includes 'photos_by' if present
            if "photos_by" in href or "tab=photos_by" in href or "a=1" in href:
                target_link = href
        if which == "of" and ("photos of" in t or "photos of " in t):
            if "photos_of" in href or "tab=photos_of" in href:
                target_link = href
    # Fall back to direct suffixes
    if not target_link:
        target_link = abs_mbasic(base + ("/photos_by" if which == "by" else "/photos_of"))
    else:
        target_link = abs_mbasic(target_link)

    collected: List[str] = []
    next_url = target_link
    visited_page_urls = set()

    while next_url and len(collected) < limit:
        if next_url in visited_page_urls:
            break
        visited_page_urls.add(next_url)
        driver.get(next_url)
        rs()
        doc = soup(driver.page_source)
        # collect photo.php links on the page
        for a in doc.select("a[href*='photo.php']"):
            href = a.get("href") or ""
            if "fbid=" in href:
                full = abs_mbasic(href)
                if full not in collected:
                    collected.append(full)
                    if len(collected) >= limit:
                        break
        if len(collected) >= limit:
            break
        # find pagination "See More" link
        nxt = None
        for a in doc.select("a"):
            txt = (a.text or "").strip().lower()
            if txt in ("see more", "see more photos"):
                href = a.get("href") or ""
                if href:
                    nxt = abs_mbasic(href)
                    break
        next_url = nxt

    return collected

def extract_caption(doc: BS) -> str:
    # Try typical containers around the photo content on mbasic
    # 1) divs near "Like" or "Write a comment" often hold story text
    candidates = []
    for d in doc.select("div"):
        txt = d.get_text(" ", strip=True)
        if txt and 2 < len(txt) < 2000:
            # heuristic: include some trigger words or the presence near a "Like" link
            if any(k in txt.lower() for k in ["like", "comment", "share"]):
                continue
            candidates.append(txt)
    # pick a reasonable short-ish line close to top
    for c in candidates[:10]:
        # reject dates only
        if len(c) > 3:
            return c
    # fallback: title
    t = doc.find("title")
    if t and t.text:
        return t.text.strip()
    return ""

def find_fullsize_image_link(doc: BS) -> Optional[str]:
    # mbasic often has "View Full Size"
    a = doc.find("a", string=re.compile(r"view full size", re.I))
    if a and a.get("href"):
        return abs_mbasic(a["href"])
    return None

def extract_main_image_b64(driver, req_sess, doc: BS) -> str:
    # Try full-size first
    full = find_fullsize_image_link(doc)
    if full:
        try:
            driver.get(full)
            rs()
            d2 = soup(driver.page_source)
            img = d2.find("img", src=True)
            if img:
                return download_b64(req_sess, abs_mbasic(img["src"]))
        except Exception:
            pass
    # Fallback: any scontent img on current page
    img = doc.find("img", src=re.compile(r"scontent"))
    if img:
        return download_b64(req_sess, abs_mbasic(img["src"]))
    return ""

def extract_reactions(driver) -> List[Dict[str, str]]:
    """Open reactions browser if link is present, return list of users with profile links."""
    page = soup(driver.page_source)
    link = None
    # seek reactions link
    for a in page.select("a[href*='/ufi/reaction/profile/browser/']"):
        link = abs_mbasic(a.get("href"))
        break
    if not link:
        return []
    # navigate
    out = []
    visited = set()
    next_url = link
    while next_url and len(out) < MAX_REACTIONS:
        driver.get(next_url)
        rs()
        doc = soup(driver.page_source)
        for a in doc.select("a"):
            name = (a.text or "").strip()
            href = a.get("href") or ""
            if not name or not href:
                continue
            if re.search(r"^/(profile\.php\?id=\d+|[A-Za-z0-9\.\-_]+)(/)?(\?|$)", href):
                full = abs_mbasic(href)
                key = (name, full)
                if key not in visited:
                    visited.add(key)
                    out.append({"name": name, "url": full})
        # pagination
        nxt = None
        for a in doc.select("a"):
            if (a.text or "").strip().lower() in ("see more", "more"):
                h = a.get("href") or ""
                if h:
                    nxt = abs_mbasic(h)
                    break
        next_url = nxt
    return out

def extract_comments(driver) -> List[Dict[str, str]]:
    """
    Heuristic: parse the current photo/story page and collect (user, url, text).
    """
    doc = soup(driver.page_source)
    comments: List[Dict[str, str]] = []

    # Comment blocks often live near anchors with profile links followed by text spans
    # Strategy: find divs that contain an <a> to a profile and a following text node/span.
    for d in doc.select("div"):
        a = d.find("a", href=True)
        if not a:
            continue
        name = (a.text or "").strip()
        href = a.get("href") or ""
        if not name or not href:
            continue
        if not re.search(r"^/(profile\.php\?id=\d+|[A-Za-z0-9\.\-_]+)(/)?(\?|$)", href):
            continue
        # try to find the text that is not the username
        # grab the div text and subtract name
        text = d.get_text(" ", strip=True)
        if not text:
            continue
        # remove username at start
        if text.startswith(name):
            text = text[len(name):].strip(" :-\u00a0")
        # basic filter to avoid picking non-comment things
        if text and len(text) > 1 and len(text) < 1200:
            comments.append({"name": name, "url": abs_mbasic(href), "text": text})
        if len(comments) >= MAX_COMMENTS:
            break
    # De-dup
    seen = set()
    uniq = []
    for c in comments:
        key = (c["name"], c["url"], c["text"])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq

def scrape_photo_detail(driver, req_sess: requests.Session, photo_url: str) -> Dict[str, Any]:
    driver.get(photo_url)
    rs()
    doc = soup(driver.page_source)
    caption = extract_caption(doc)
    img_b64 = extract_main_image_b64(driver, req_sess, doc)
    reactions = extract_reactions(driver)
    comments = extract_comments(driver)
    return {
        "url": photo_url,
        "caption": caption,
        "image_b64": img_b64,
        "reactions": reactions,
        "comments": comments,
    }

# ------------- HTML builder -------------
def esc(s: str) -> str:
    return html.escape(s or "")

def user_link(name: str, url: str) -> str:
    return f'<a href="{esc(url)}">{esc(name)}</a>'

def build_html(out_path: str,
               header: Dict[str, Any],
               about: Dict[str, List[str]],
               friends: List[Dict[str, str]],
               photos_by: List[Dict[str, Any]],
               photos_of: List[Dict[str, Any]]):

    def section(title: str, inner: str) -> str:
        return f'<div class="section"><h2>{esc(title)}</h2>{inner}</div>'

    def dl(items: List[str]) -> str:
        return "<ul class='list'>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"

    def friends_html(lst: List[Dict[str, str]]) -> str:
        return "<ul class='list'>" + "".join(f"<li>{user_link(x['name'], x['url'])}</li>" for x in lst) + "</ul>"

    def reactions_html(lst: List[Dict[str, str]]) -> str:
        return "<ul class='list small'>" + "".join(f"<li>{user_link(x['name'], x['url'])}</li>" for x in lst) + "</ul>"

    def comments_html(lst: List[Dict[str, str]]) -> str:
        return "<ul class='list'>" + "".join(
            f"<li>{user_link(x['name'], x['url'])}: {esc(x.get('text',''))}</li>" for x in lst
        ) + "</ul>"

    def photo_card(p: Dict[str, Any], idx: int, kind: str) -> str:
        img = p.get("image_b64") or ""
        cap = p.get("caption") or ""
        reacts = p.get("reactions") or []
        cmts = p.get("comments") or []
        link = p.get("url") or "#"
        parts = [f'<div class="card"><div class="meta"><a href="{esc(link)}">{esc(kind)} {idx}</a></div>']
        if img:
            parts.append(f'<img class="media" src="{img}" alt="photo">')
        if cap:
            parts.append(f"<div><strong>Caption</strong><br><pre>{esc(cap)}</pre></div>")
        parts.append(f"<details><summary>Reactions — {len(reacts)}</summary><div class='content'>{reactions_html(reacts)}</div></details>")
        parts.append(f"<details><summary>Comments — {len(cmts)}</summary><div class='content'>{comments_html(cmts)}</div></details>")
        parts.append("</div>")
        return "\n".join(parts)

    intro_lines = header.get("intro") or []
    ppic = header.get("profile_pic_b64") or ""
    name = header.get("name") or ""
    slug = header.get("slug") or ""

    about_blocks = []
    for k, vals in about.items():
        if not vals:
            continue
        about_blocks.append(f"<details><summary>{esc(k)}</summary><div class='content'>{dl(vals)}</div></details>")

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Facebook Report - {esc(name or slug)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0b0c10;color:#e6edf3;margin:0;padding:20px}}
a{{color:#6ab7ff;text-decoration:none}} a:hover{{text-decoration:underline}}
h1,h2,h3{{margin:0 0 10px}}
.section{{margin:26px 0}}
.header{{display:flex;gap:16px;align-items:center}}
.avatar{{width:100px;height:100px;border-radius:50%;object-fit:cover;border:2px solid #1f6feb}}
.kpis{{display:flex;gap:10px;margin:8px 0}}
.card{{background:#0e1117;border:1px solid #1f2937;border-radius:12px;padding:12px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
.media{{width:100%;border-radius:8px;display:block;margin-bottom:8px}}
.list{{list-style:none;padding:0;margin:0}}
.list li{{padding:6px 0;border-bottom:1px solid #1f2937}}
.list.small li{{padding:4px 0;font-size:0.95em}}
details{{background:#0e1117;border:1px solid #1f2937;border-radius:10px;margin:8px 0}}
details > summary{{cursor:pointer;padding:10px;font-weight:600;list-style:none;display:block}}
details > summary::after{{content:'▸'; float:right; color:#9aa4b2;}}
details[open] > summary{{border-bottom:1px solid #1f2937}}
details[open] > summary::after{{content:'▾'}}
details .content{{padding:10px;overflow:auto}}
pre{{white-space:pre-wrap}}
.muted{{color:#9aa4b2}}
</style>
</head>
<body>
<h1>Facebook Report — {esc(name or slug)}</h1>
<div class="section header">
{"<img class='avatar' src='%s' alt='avatar'>" % esc(ppic) if ppic else ""}
<div>
  <h2>{esc(name or slug)}</h2>
  <div class="muted">Profile: <a href="https://www.facebook.com/{esc(slug)}">facebook.com/{esc(slug)}</a></div>
  {"<div><strong>Intro</strong><br><pre>%s</pre></div>" % esc("\\n".join(intro_lines)) if intro_lines else ""}
</div>
</div>

<div class="section">
  <h2>About</h2>
  {"".join(about_blocks) if about_blocks else "<div class='muted'>No public About details found.</div>"}
</div>

<div class="section">
  <details open><summary>Friends — {len(friends)}</summary>
    <div class="content">
      {friends_html(friends)}
    </div>
  </details>
</div>

<div class="section">
  <h2>Photos by User</h2>
  <div class="grid">
    {"".join(photo_card(p, i+1, "Photo") for i, p in enumerate(photos_by))}
  </div>
</div>

<div class="section">
  <h2>Photos of User (Tagged)</h2>
  <div class="grid">
    {"".join(photo_card(p, i+1, "Tagged") for i, p in enumerate(photos_of))}
  </div>
</div>

</body></html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"[i] HTML saved → {os.path.abspath(out_path)}")

# ------------- Main -------------
def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, ".env")
    raw_cookie = read_raw_cookie_from_env(env_path)

    profile_in = input("Enter Facebook profile URL to scrape: ").strip()
    if not profile_in:
        print("[ERROR] Need a profile URL.")
        return
    profile_url = ensure_mbasic(profile_in)
    # normalize trailing slash
    if not profile_url.endswith("/"):
        profile_url += "/"

    # Selenium + cookie login
    driver = build_driver(HEADLESS)
    try:
        login_with_raw_cookie(driver, raw_cookie)
        # quick check: user menu exists?
        # (Not strictly needed; if cookie is bad, subsequent pages might redirect to login)

        # Requests session (to fetch images for Base64)
        req_sess = make_requests_session(raw_cookie)

        print("[i] Header / Intro ...")
        header = get_profile_header(driver, req_sess, profile_url)

        print("[i] About sections ...")
        about = scrape_about_sections(driver, profile_url)

        print(f"[i] Friends (up to {MAX_FRIENDS}) ...")
        friends = scrape_friends(driver, profile_url, limit=MAX_FRIENDS)

        print(f"[i] Collecting Photo links — uploads (up to {MAX_PHOTOS_BY}) ...")
        photo_links_by = collect_photo_links(driver, profile_url, which="by", limit=MAX_PHOTOS_BY)

        print(f"[i] Collecting Photo links — tagged (up to {MAX_PHOTOS_OF}) ...")
        photo_links_of = collect_photo_links(driver, profile_url, which="of", limit=MAX_PHOTOS_OF)

        print(f"[i] Scraping details for {len(photo_links_by)} uploaded photos ...")
        photos_by = []
        for i, u in enumerate(photo_links_by, start=1):
            print(f"    - Photo {i}/{len(photo_links_by)}")
            try:
                photos_by.append(scrape_photo_detail(driver, req_sess, u))
            except Exception as e:
                print(f"      [WARN] photo failed: {e}")
            rs()

        print(f"[i] Scraping details for {len(photo_links_of)} tagged photos ...")
        photos_of = []
        for i, u in enumerate(photo_links_of, start=1):
            print(f"    - Tagged {i}/{len(photo_links_of)}")
            try:
                photos_of.append(scrape_photo_detail(driver, req_sess, u))
            except Exception as e:
                print(f"      [WARN] tagged failed: {e}")
            rs()

        out_name = (header.get("slug") or "facebook_report") + ".html"
        build_html(out_name, header, about, friends, photos_by, photos_of)
        print("[i] Done.")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
