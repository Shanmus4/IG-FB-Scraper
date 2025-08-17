#!/usr/bin/env python3
"""
facebook_singlefile_deterministic.py

Deterministic flow:
1) Prompt for Facebook profile URL
2) Read raw cookie string from .env (raw format)
3) Build a temporary controller extension bundling SingleFile lib/
4) Launch Chromium persistent context with that extension
5) Inject cookies (domain .facebook.com)
6) For each target page in order:
   - profile main
   - about (via real About link on profile page)
   - friends (via real Friends link)
   - photos (via Photos link)
   - photos tagged (if link exists)
   - videos (via Videos link)
   - videos tagged (if link exists)
   Do: navigate -> wait until stable -> perform focused expansions -> trigger SingleFile capture -> write file
7) Create master HTML file with iframes to snapshots
8) Optionally cleanup generated extension and profile folder

Requirements:
 - SingleFile repo present in ./SingleFile with lib/ folder (repo: https://github.com/gildas-lormeau/SingleFile)
 - .env present in same folder with raw cookie string (semicolon-separated) copied from www.facebook.com
 - Playwright installed (pip install playwright; playwright install)
"""
import os
import re
import time
import json
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------- Config ----------------
ROOT = Path.cwd()
SINGLEFILE_REPO = ROOT / "SingleFile"
EXT_DIR = ROOT / "sf_singlefile_controller_ext"
USER_DATA_DIR = ROOT / ".sf_playwright_profile"
ENV_FILE = ROOT / ".env"
SNAPSHOT_DIR_TEMPLATE = "{profile_id}_snapshots"
MASTER_TEMPLATE = "{profile_id}_facebook.html"

# Tunables
WAIT_AFTER_NAV = 2.0
STABLE_CHECK_INTERVAL = 0.5
STABLE_ROUNDS = 3
STABLE_TIMEOUT = 15
SINGLEFILE_TIMEOUT_MS = 180000  # 3 minutes for SingleFile capture
MAX_FRIEND_SCROLLS = 10
MAX_FEED_SCROLLS = 6
REMOVE_TEMP_AT_END = True  # set False if you want to inspect extension/profile directories

# Cookie domain: use .facebook.com to cover www and subdomains
COOKIE_DOMAIN = ".facebook.com"
COOKIE_PATH = "/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fb_singlefile")

# ---------------- Helpers: cookies ----------------
def read_cookie_from_env(env_path: Path = ENV_FILE) -> str:
    if not env_path.exists():
        raise FileNotFoundError(f".env not found at {env_path}")
    raw = env_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(".env appears empty")
    # heuristics: if multiline, find the long semicolon separated line
    if "\n" in raw or ("=" in raw and ";" in raw):
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        # pick the line which seems like cookies (many '=' and ';')
        cand = max(lines, key=lambda L: (L.count(";"), len(L)))
        return cand
    return raw

def parse_cookie_string_to_playwright(raw: str, domain: str = COOKIE_DOMAIN, path: str = COOKIE_PATH) -> List[Dict]:
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    cookies = []
    for p in parts:
        if "=" not in p:
            continue
        name, val = p.split("=", 1)
        name = name.strip()
        val = val.strip()
        if not name:
            continue
        cookies.append({
            "name": name,
            "value": val,
            "domain": domain,
            "path": path,
            # do not force httpOnly; leaving false allows Playwright to set them.
            "httpOnly": False,
            "secure": True
        })
    return cookies

# ---------------- Build controller extension ----------------
def build_controller_extension(singlefile_repo_dir: Path, ext_dir: Path):
    logger.info("Building controller extension at %s", ext_dir)
    if ext_dir.exists():
        shutil.rmtree(ext_dir)
    ext_dir.mkdir(parents=True, exist_ok=True)

    lib_src = singlefile_repo_dir / "lib"
    if not lib_src.exists():
        raise FileNotFoundError(f"SingleFile lib not found at {lib_src}. Clone the repo there.")
    shutil.copytree(lib_src, ext_dir / "lib")

    # background.html to load background scripts (keeps extension valid)
    background_html = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<script src="lib/chrome-browser-polyfill.js"></script>
<script src="lib/single-file-background.js"></script>
</body></html>"""
    (ext_dir / "background.html").write_text(background_html, encoding="utf-8")

    # content script: listens for window.postMessage requests from page and calls extension.getPageData
    content_script = r"""
(function () {
  if (window.__singlefile_controller_installed) return;
  window.__singlefile_controller_installed = true;
  window.addEventListener('message', async function (event) {
    try {
      const d = event.data;
      if (!d || d.source !== 'singlefile-controller-request') return;
      const id = d.id || 'capture';
      const options = d.options || {};
      if (typeof extension === 'undefined' || !extension.getPageData) {
        window.postMessage({ source: 'singlefile-controller-response', id: id, error: 'SingleFile not ready (extension.getPageData missing)' }, '*');
        return;
      }
      try {
        const result = await extension.getPageData(options);
        window.postMessage({ source: 'singlefile-controller-response', id: id, title: result.title, filename: result.filename, content: result.content }, '*');
      } catch (err) {
        window.postMessage({ source: 'singlefile-controller-response', id: id, error: err && err.message ? err.message : String(err) }, '*');
      }
    } catch (e) {
      // ignore
    }
  }, false);
})();
"""
    (ext_dir / "content_script.js").write_text(content_script, encoding="utf-8")

    manifest = {
        "manifest_version": 2,
        "name": "SingleFile Controller for Playwright",
        "version": "1.0",
        "description": "Controller bundling SingleFile lib and exposing capture bridge",
        "content_scripts": [
            {
                "matches": ["<all_urls>"],
                "js": [
                    "lib/chrome-browser-polyfill.js",
                    "lib/single-file-frames.js",
                    "lib/single-file-extension-frames.js"
                ],
                "run_at": "document_start",
                "all_frames": True
            },
            {
                "matches": ["<all_urls>"],
                "js": [
                    "lib/chrome-browser-polyfill.js",
                    "lib/single-file-bootstrap.js",
                    "lib/single-file-extension-core.js",
                    "lib/single-file.js",
                    "content_script.js"
                ],
                "run_at": "document_idle",
                "all_frames": False
            }
        ],
        "background": {"page": "background.html", "persistent": False},
        "permissions": ["activeTab", "<all_urls>"],
        "web_accessible_resources": ["lib/single-file-hooks-frames.js"]
    }
    (ext_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Controller extension created")

# ---------------- DOM helpers (deterministic) ----------------
def wait_for_page_stable(page, check_interval=STABLE_CHECK_INTERVAL, stable_rounds=STABLE_ROUNDS, timeout=STABLE_TIMEOUT):
    start = time.time()
    last = None
    stable = 0
    while True:
        try:
            h = page.evaluate("() => document.body.scrollHeight")
        except Exception:
            h = None
        if h == last:
            stable += 1
        else:
            stable = 0
        last = h
        if stable >= stable_rounds:
            logger.debug("Page stable detected")
            return True
        if time.time() - start > timeout:
            logger.debug("Page stable wait timed out")
            return False
        time.sleep(check_interval)

def auto_scroll_page(page, max_rounds=6, pause=1.0):
    prev = -1
    for i in range(max_rounds):
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(pause)
        cur = page.evaluate("() => document.body.scrollHeight")
        if cur == prev:
            return
        prev = cur

def click_expandors(page, patterns=None, max_iter=6):
    if patterns is None:
        patterns = ["See more", "See More", "see more", "See original", "See translation", "View more comments", "See more comments", "View more replies", "Load more comments"]
    for _ in range(max_iter):
        clicked = False
        for pat in patterns:
            try:
                loc = page.locator(f"text=\"{pat}\"")
                c = loc.count()
                for i in range(c):
                    try:
                        loc.nth(i).scroll_into_view_if_needed(timeout=1500)
                        loc.nth(i).click(timeout=1500)
                        clicked = True
                        time.sleep(0.12)
                    except Exception:
                        pass
            except Exception:
                pass
        if not clicked:
            break

# ---------------- SingleFile bridge ----------------
def setup_page_result_listener(page):
    page.evaluate(r"""
() => {
  if (window.__singlefile_results_installed) return;
  window.__singlefile_results_installed = true;
  window.__singlefile_results = window.__singlefile_results || {};
  window.addEventListener('message', function (e) {
    try {
      const d = e.data;
      if (!d || d.source !== 'singlefile-controller-response') return;
      const id = d.id || 'capture';
      window.__singlefile_results[id] = { title: d.title, filename: d.filename, content: d.content, error: d.error };
    } catch (err) { console.warn('sf listener err', err); }
  }, false);
}
""")

def request_singlefile_capture_and_wait(page, capture_id: str, timeout_ms: int = SINGLEFILE_TIMEOUT_MS) -> Dict:
    logger.info("Requesting SingleFile capture: %s", capture_id)
    setup_page_result_listener(page)
    page.evaluate(f"() => {{ if (window.__singlefile_results) delete window.__singlefile_results['{capture_id}']; }}")
    # post request to extension content script
    page.evaluate(f"""
() => {{
  window.postMessage({{ source: 'singlefile-controller-request', id: '{capture_id}', options: {{ removeHiddenElements: true, compressHTML: true, blockVideos: false }} }}, '*');
}}
""")
    try:
        page.wait_for_function(f"() => window.__singlefile_results && window.__singlefile_results['{capture_id}'] !== undefined", timeout=timeout_ms)
    except PWTimeout:
        raise TimeoutError(f"Timed out waiting for SingleFile capture id {capture_id}")
    res = page.evaluate(f"() => window.__singlefile_results['{capture_id}']")
    if not res:
        raise RuntimeError("Empty SingleFile response for " + capture_id)
    if res.get("error"):
        logger.warning("SingleFile returned error for %s: %s", capture_id, res.get("error"))
    return res

# ---------------- Helpers to find real page links on profile ----------------
def find_profile_link_target(page, keywords: List[str]) -> Optional[str]:
    """
    Search for an anchor on the current page whose visible text matches any keyword.
    Return absolute href or None.
    """
    # Use evaluate to find visible anchors matching text heuristics and return first href
    try:
        js = r"""
(keywords) => {
  const anchors = Array.from(document.querySelectorAll('a'));
  for (const a of anchors) {
    if (!a || !a.textContent) continue;
    const txt = a.textContent.trim();
    for (const k of keywords) {
      if (!k) continue;
      if (txt.toLowerCase().includes(k.toLowerCase())) {
        const h = a.getAttribute('href');
        if (h) {
          // normalize to full URL
          if (h.startsWith('http')) return h;
          if (h.startsWith('/')) return window.location.origin + h;
          return window.location.origin + '/' + h;
        }
      }
    }
  }
  return null;
}
"""
        href = page.evaluate(js, keywords)
        return href
    except Exception as e:
        logger.debug("find_profile_link_target error: %s", e)
        return None

def find_anchor_href_by_href_pattern(page, pattern: str) -> Optional[str]:
    """
    Find anchor with href containing pattern and return absolute url if found.
    """
    try:
        js = r"""
(pat) => {
  const anchors = Array.from(document.querySelectorAll('a'));
  for (const a of anchors) {
    const h = a.getAttribute('href') || '';
    if (h.indexOf(pat) !== -1) {
      if (h.startsWith('http')) return h;
      if (h.startsWith('/')) return window.location.origin + h;
      return window.location.origin + '/' + h;
    }
  }
  return null;
}
"""
        href = page.evaluate(js, pattern)
        return href
    except Exception as e:
        logger.debug("find_anchor_href_by_href_pattern error: %s", e)
        return None

# ---------------- Save snapshot to disk ----------------
def save_snapshot_content(res: Dict, out_dir: Path, profile_id: str, short_name: str) -> Path:
    fn = res.get("filename") or f"{profile_id}_{short_name}.html"
    fn = re.sub(r"[^\w\-_\. ]", "_", fn)[:200]
    out_path = out_dir / fn
    content = res.get("content", "")
    out_path.write_text(content, encoding="utf-8")
    logger.info("Saved snapshot %s", out_path)
    return out_path

# ---------------- Orchestrator (deterministic flow) ----------------
def run(profile_url: str):
    if not SINGLEFILE_REPO.exists() or not (SINGLEFILE_REPO / "lib").exists():
        raise FileNotFoundError("SingleFile repo with lib/ not found at ./SingleFile")

    raw_cookie = read_cookie_from_env()
    cookies = parse_cookie_string_to_playwright(raw_cookie, domain=COOKIE_DOMAIN, path=COOKIE_PATH)
    logger.info("Parsed %d cookies", len(cookies))

    build_controller_extension(SINGLEFILE_REPO, EXT_DIR)

    # Launch persistent Chromium so extension loads
    logger.info("Launching Chromium persistent context with controller extension")
    Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
    args = [f"--disable-extensions-except={str(EXT_DIR)}", f"--load-extension={str(EXT_DIR)}"]
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(USER_DATA_DIR), headless=False, args=args)
        page = context.new_page()

        # Inject cookies
        try:
            context.add_cookies(cookies)
            logger.info("Injected cookies into context")
        except Exception as e:
            logger.warning("context.add_cookies failed: %s; will retry via page navigation", e)
            try:
                page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=30000)
                for c in cookies:
                    try:
                        context.add_cookies([c])
                    except Exception:
                        pass
            except Exception:
                pass

        # Visit profile main
        logger.info("Visiting profile: %s", profile_url)
        page.goto(profile_url, wait_until="load", timeout=60000)
        time.sleep(WAIT_AFTER_NAV)
        wait_for_page_stable(page)
        click_expandors(page)
        # capture profile main
        try:
            res = request_singlefile_capture_and_wait(page, "profile_main", timeout_ms=SINGLEFILE_TIMEOUT_MS)
        except Exception as e:
            logger.exception("SingleFile capture for profile_main failed: %s", e)
            res = {"content": page.content(), "filename": "profile_main_fallback.html", "title": "profile_fallback"}
        # detect profile id
        html = page.content()
        profile_id = None
        m = re.search(r'"userID"\s*:\s*"(\d+)"', html)
        if m:
            profile_id = m.group(1)
        else:
            m2 = re.search(r'profile_owner[^\d]*(\d+)', html) or re.search(r'entity_id[^\d]*(\d+)', html)
            if m2:
                profile_id = m2.group(1)
        if not profile_id:
            m3 = re.search(r"profile\.php\?id=(\d+)", profile_url)
            if m3:
                profile_id = m3.group(1)
        if not profile_id:
            profile_id = "unknown_profile"
            logger.warning("Could not detect profile id; using %s", profile_id)

        out_root = Path(SNAPSHOT_DIR_TEMPLATE.format(profile_id=profile_id))
        out_root.mkdir(parents=True, exist_ok=True)

        save_snapshot_content(res, out_root, profile_id, "profile_main")

        # Helper to visit by finding links on the profile or current page, and capture deterministically
        def visit_and_capture_by_text_or_pattern(page, text_keywords: List[str], href_pattern: Optional[str], fallback_construct: Optional[str], capture_suffix: str, scroll_rounds=0):
            """
            Try to find a link by visible text keywords first on current page; if not found try href_pattern
            If both fail and fallback_construct is provided, use it.
            """
            # Try visible link first on current document
            href = find_profile_link_target(page, text_keywords) if text_keywords else None
            if not href and href_pattern:
                href = find_anchor_href_by_href_pattern(page, href_pattern)
            if not href and fallback_construct:
                href = fallback_construct
            if not href:
                logger.warning("Unable to find target for %s (keywords=%s pattern=%s). Skipping.", capture_suffix, text_keywords, href_pattern)
                return None
            logger.info("Visiting target for %s -> %s", capture_suffix, href)
            page.goto(href, wait_until="load", timeout=60000)
            time.sleep(WAIT_AFTER_NAV)
            if scroll_rounds and scroll_rounds > 0:
                auto_scroll_page(page, max_rounds=scroll_rounds, pause=1.0)
            click_expandors(page)
            wait_for_page_stable(page)
            try:
                res = request_singlefile_capture_and_wait(page, capture_suffix, timeout_ms=SINGLEFILE_TIMEOUT_MS)
            except Exception as e:
                logger.exception("SingleFile capture %s failed: %s. Falling back to page.content()", capture_suffix, e)
                res = {"content": page.content(), "filename": f"{capture_suffix}_fallback.html", "title": capture_suffix}
            return save_snapshot_content(res, out_root, profile_id, capture_suffix)

        # 1) About (try About link text)
        visit_and_capture_by_text_or_pattern(page, ["About"], "/about", profile_url.rstrip("/") + "/about", "about_overview", scroll_rounds=1)
        visit_and_capture_by_text_or_pattern(page, ["Contact and basic info", "Contact info", "Contact"], "contact_and_basic_info", None, "about_contact_and_basic_info", scroll_rounds=1)
        visit_and_capture_by_text_or_pattern(page, ["Family and relationships", "Family"], "family_and_relationships", None, "about_family_and_relationships", scroll_rounds=1)

        # 2) Friends
        visit_and_capture_by_text_or_pattern(page, ["Friends"], "/friends", profile_url.rstrip("/") + "/friends", "friends", scroll_rounds=MAX_FRIEND_SCROLLS)

        # 3) Photos (by / uploads)
        visit_and_capture_by_text_or_pattern(page, ["Photos"], "/photos", profile_url.rstrip("/") + "/photos", "photos_by", scroll_rounds=MAX_FEED_SCROLLS)
        # 4) Photos tagged (if available)
        visit_and_capture_by_text_or_pattern(page, ["Photos of", "Tagged"], "photos_tagged", None, "photos_of", scroll_rounds=MAX_FEED_SCROLLS)

        # 5) Videos
        visit_and_capture_by_text_or_pattern(page, ["Videos"], "/videos", profile_url.rstrip("/") + "/videos", "videos_by", scroll_rounds=MAX_FEED_SCROLLS)
        visit_and_capture_by_text_or_pattern(page, ["Videos of", "Tagged videos"], "videos_tagged", None, "videos_of", scroll_rounds=MAX_FEED_SCROLLS)

        # create master index
        logger.info("Creating master index HTML")
        snapshots = sorted([p for p in out_root.iterdir() if p.is_file() and p.suffix == ".html"])
        master_path = ROOT / MASTER_TEMPLATE.format(profile_id=profile_id)
        with open(master_path, "w", encoding="utf-8") as mf:
            mf.write("<!doctype html>\n<html>\n<head>\n<meta charset='utf-8'>\n")
            mf.write(f"<title>Facebook export {profile_id}</title>\n")
            mf.write("<style>body{font-family:Arial,Helvetica,sans-serif;margin:18px} iframe{width:100%;height:720px;border:1px solid #ddd;margin-bottom:18px}</style>\n")
            mf.write("</head>\n<body>\n")
            mf.write(f"<h1>Export for profile {profile_id}</h1>\n")
            for s in snapshots:
                rel = os.path.relpath(str(s), start=str(master_path.parent))
                mf.write(f"<details>\n<summary style='font-size:16px;padding:8px'>{s.name}</summary>\n<iframe src=\"{rel}\" loading='lazy'></iframe>\n</details>\n")
            mf.write("</body>\n</html>\n")
        logger.info("Master index created at %s", master_path)

        # close context
        logger.info("Closing context and browser")
        context.close()

    # cleanup ext and profile folders if desired
    if REMOVE_TEMP_AT_END:
        try:
            if EXT_DIR.exists():
                shutil.rmtree(EXT_DIR)
            if USER_DATA_DIR.exists():
                shutil.rmtree(USER_DATA_DIR)
            logger.info("Removed temporary extension and profile folders")
        except Exception as e:
            logger.warning("Cleanup error: %s", e)

    logger.info("Done. Snapshots in %s and master %s", out_root, master_path)

# ---------------- Entry point ----------------
if __name__ == "__main__":
    try:
        profile_url = input("Paste full Facebook profile URL (www.facebook.com/...) and press Enter: ").strip()
        if not profile_url:
            print("Profile URL cannot be empty. Exiting.")
            raise SystemExit(1)
        run(profile_url)
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        raise
