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
import uuid
from typing import List, Dict, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------- Config ----------------
ROOT = Path.cwd()
SINGLEFILE_REPO = ROOT / "SingleFile"
EXT_DIR = ROOT / "sf_singlefile_controller_ext"
# Use unique profile dir to allow parallel execution of multiple scripts
USER_DATA_DIR = ROOT / f".sf_playwright_profile_{uuid.uuid4().hex}"
ENV_FILE = ROOT / ".env"
SNAPSHOT_DIR_TEMPLATE = "{profile_id}_snapshots"
MASTER_TEMPLATE = "{profile_id}_facebook.html"

# Tunables
WAIT_AFTER_NAV = 2.0
STABLE_CHECK_INTERVAL = 0.5
STABLE_ROUNDS = 3
STABLE_TIMEOUT = 15
SINGLEFILE_TIMEOUT_MS = 180000  # 3 minutes for SingleFile capture
MAX_FRIEND_SCROLLS = 25
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

    # background.js (Service Worker) for Manifest V3
    background_js = """
try {
  importScripts('lib/chrome-browser-polyfill.js', 'lib/single-file-background.js');
} catch (e) {
  console.error(e);
}
"""
    (ext_dir / "background.js").write_text(background_js, encoding="utf-8")

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
        "manifest_version": 3,
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
        "background": {"service_worker": "background.js"},
        "permissions": ["activeTab", "scripting"],
        "host_permissions": ["<all_urls>"],
        "web_accessible_resources": [
            {
                "resources": ["lib/single-file-hooks-frames.js"],
                "matches": ["<all_urls>"]
            }
        ]
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

def auto_scroll_page(page, max_rounds=6, pause=1.0, step_callback=None):
    prev = -1
    no_change_count = 0
    max_no_change = 10

    for i in range(max_rounds):
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        
        # Sleep in chunks to allow callback execution
        waited = 0.0
        chunk = 0.2
        while waited < pause:
            time.sleep(chunk)
            waited += chunk
            if step_callback:
                step_callback()
        
        cur = page.evaluate("() => document.body.scrollHeight")
        if cur == prev:
            no_change_count += 1
            if no_change_count >= max_no_change:
                return
        else:
            no_change_count = 0
            
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

def trigger_singlefile_capture(page, capture_id: str):
    logger.info("Triggering SingleFile capture (background): %s", capture_id)
    setup_page_result_listener(page)
    # Clear old results
    page.evaluate(f"() => {{ if (window.__singlefile_results) delete window.__singlefile_results['{capture_id}']; }}")
    # Post message
    page.evaluate(f"""
    () => {{
      window.postMessage({{ 
        source: 'singlefile-controller-request', 
        id: '{capture_id}', 
        options: {{ 
            removeHiddenElements: true,
            compressHTML: true,
            blockScripts: true,
            blockAudios: true,
            blockVideos: true,
            removeUnusedStyles: true,
            removeUnusedFonts: true,
            removeAlternativeImages: true,
            removeAlternativeFonts: true,
            removeAlternativeMedias: true,
            groupDuplicateImages: true,
            loadDeferredImages: true,
            maxResourceSizeEnabled: false,
            blockMixedContent: false
        }} 
      }}, '*');
    }}
    """)

def collect_singlefile_result(page, capture_id: str):
    # Check if result exists. If not, returns None immediately (non-blocking check logic, but we usually want to wait if we call this)
    # This specific helper is designed to Poll or Wait. 
    # For the pipeline, we might want a non-blocking "check".
    res = page.evaluate(f"() => window.__singlefile_results && window.__singlefile_results['{capture_id}']")
    return res

def request_singlefile_capture_and_wait(page, capture_id: str, timeout_ms: int = SINGLEFILE_TIMEOUT_MS) -> Dict:
    trigger_singlefile_capture(page, capture_id)
    try:
        page.wait_for_function(f"() => window.__singlefile_results && window.__singlefile_results['{capture_id}'] !== undefined", timeout=timeout_ms)
    except PWTimeout:
        raise TimeoutError(f"Timed out waiting for SingleFile capture id {capture_id}")
    
    res = collect_singlefile_result(page, capture_id)
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
    # Force our own robust naming scheme
    # timestamp to ensure uniqueness if multiple runs or similar items
    fn = f"{profile_id}_{short_name}.html"
    # sanitize
    fn = re.sub(r"[^\w\-_\. ]", "_", fn)[:200]
    out_path = out_dir / fn
    content = res.get("content", "")
    
    # Ensure extension is .html
    if not out_path.name.lower().endswith(".html"):
        out_path = out_path.with_suffix(".html")
        
    out_path.write_text(content, encoding="utf-8")
    logger.info("Saved snapshot %s", out_path.name)
    return out_path

def sanitize_url_to_folder(url: str) -> str:
    # strip protocol
    s = re.sub(r'https?://(www\.)?', '', url)
    # replace illegal chars
    s = re.sub(r'[\\/:*?"<>|]', '_', s)
    return s.strip()

def expand_reactions_modal(page):
    """
    Attempt to click the reactions count (e.g., the number '3') to open the 'People who reacted' modal,
    then scroll that modal to load more users.
    """
    logger.info("Attempting to expand reactions modal...")
    try:
        found = False
        
        # Strategy: Click the numeric text itself. 
        # The user provided screenshot shows "LikeIcon HeartIcon 3". 
        # We want to click the "3".
        
        try:
            # Execute JS to find the specific numeric element
            page.evaluate("""() => {
                // Helper to check visibility
                function isVisible(elem) {
                    if (!(elem instanceof Element)) return false;
                    const style = getComputedStyle(elem);
                    if (style.display === 'none') return false;
                    if (style.visibility !== 'visible') return false;
                    if (style.opacity === '0') return false;
                    return true;
                }

                // 1. Find all visible elements containing just digits (and maybe K/M suffixes)
                // We restrict search to the 'feedback' context if possible, but strict context is hard to guess.
                // We search all spans/divs.
                const elements = document.querySelectorAll('span, div[role="button"]');
                
                for (const el of elements) {
                    const text = el.innerText ? el.innerText.trim() : "";
                    
                    // Match exact number "3", or "1.5K", "You and 4 others"
                    // The screenshot shows just "3". 
                    // Regex: Start with digit, optional K/M, or "You and..."
                    if (/^([0-9.,]+[KMB]?|You and.*)/.test(text)) {
                        
                        // Heuristic: The element should be near a reaction icon.
                        // Reaction icons usually have aria-label="Like", "Love", etc. or typical emojis.
                        // We check if a sibling or parent's sibling contains an image/icon.
                        
                        // Check if this specific element is the one we want.
                        // In the screenshot, the "3" is adjacent to the icons.
                        // Often text is within a span that has a click listener.
                        
                        if (isVisible(el)) {
                            // Check ancestors for role='button' or generic clickable wrapper
                            const clickable = el.closest('[role="button"]') || el;
                            if (clickable) {
                                clickable.click();
                                return; // Stop after first match? 
                                // In a photo viewer, there's usually only one main feedback bar active/visible.
                            }
                        }
                    }
                }
            }""")
            
            # We assume the click bridged the gap. Now wait for dialog.
            page.wait_for_selector('div[role="dialog"]', state="visible", timeout=3000)
            logger.info("Reactions modal opened.")
            
            # Scroll the dialog content until end
            # We'll scroll up to 50 times or until height stops increasing
            prev_height = 0
            same_height_count = 0
            
            for i in range(50): 
                # Returns [current_scroll_top, scroll_height]
                scroll_stats = page.evaluate("""() => {
                    const dialog = document.querySelector('div[role="dialog"]');
                    if (!dialog) return [0, 0];
                    
                    const scrollables = Array.from(dialog.querySelectorAll('*')).filter(e => e.scrollHeight > e.clientHeight);
                    if (scrollables.length > 0) {
                         const target = scrollables.reduce((a, b) => a.scrollHeight > b.scrollHeight ? a : b);
                         target.scrollTop = target.scrollHeight;
                         return [target.scrollTop, target.scrollHeight];
                    }
                    return [0, 0];
                }""")
                
                curr_scrollTop, curr_height = scroll_stats
                if curr_height == 0:
                    break
                
                logger.debug(f"Reaction scroll {i+1}: height={curr_height}")
                
                if curr_height == prev_height:
                    same_height_count += 1
                    if same_height_count >= 3: # Stop if height hasn't changed for 3 iterations
                        break
                else:
                    same_height_count = 0
                
                prev_height = curr_height
                time.sleep(1.5) # Wait for network load
                
        except Exception:
            # If the numeric click didn't work or dialog didn't open
            pass

    except Exception as e:
        logger.debug("expand_reactions_modal error: %s", e)

# ---------------- Orchestrator (deterministic flow) ----------------
def run(profile_url: str):
    if not SINGLEFILE_REPO.exists() or not (SINGLEFILE_REPO / "lib").exists():
        raise FileNotFoundError("SingleFile repo with lib/ not found at ./SingleFile")

    raw_cookie = read_cookie_from_env()
    cookies = parse_cookie_string_to_playwright(raw_cookie, domain=COOKIE_DOMAIN, path=COOKIE_PATH)
    logger.info("Parsed %d cookies", len(cookies))

    build_controller_extension(SINGLEFILE_REPO, EXT_DIR)

    # Force cleanup of profile dir to reset window state preferences
    if USER_DATA_DIR.exists():
        try:
            shutil.rmtree(USER_DATA_DIR)
        except Exception as e:
            logger.warning("Could not clean old profile dir: %s", e)

    # Launch persistent Chromium so extension loads
    logger.info("Launching Chromium persistent context with controller extension")
    Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
    args = [
        f"--disable-extensions-except={str(EXT_DIR)}", 
        f"--load-extension={str(EXT_DIR)}",
        "--window-size=1920,1080",
        "--window-position=0,0"
    ]
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(USER_DATA_DIR), headless=False, args=args, viewport={"width": 1920, "height": 1080})
        
        # Use the default page created by launch_persistent_context if it exists to respect window args
        if context.pages:
            first_page = context.pages[0]
        else:
            first_page = context.new_page()

        # Inject cookies
        try:
            context.add_cookies(cookies)
            logger.info("Cookies injected")
        except Exception as e:
            logger.warning("Cookie injection warning: %s", e)
        # ---------------- Initial Setup ----------------
        # Prepare base URL for strict navigation (remove trailing slash and existing sk params)
        base_profile_url = profile_url.rstrip("/")
        # Remove existing sk= param to prevent conflicts (e.g. if user pasted a photos link)
        base_profile_url = re.sub(r'[&?]sk=[^&]*', '', base_profile_url)
        
        def construct_section_url(base: str, section: str) -> str:
            # section e.g. "photos", "about", "friends"
            if "profile.php" in base:
                if "?" in base:
                    return f"{base}&sk={section}"
                else:
                    return f"{base}?sk={section}"
            else:
                return f"{base}/{section}"

        # Profile ID detection (Simple heuristics for folder naming)
        profile_id = "fb_profile"
        m = re.search(r"id=(\d+)", base_profile_url)
        if m:
            profile_id = m.group(1)
        else:
            # maybe username? facebook.com/username
            clean = base_profile_url.split("?")[0]
            parts = [p for p in clean.split("/") if p]
            if parts: profile_id = parts[-1]
            
        # Output Structure: Facebook/{sanitized_url}/
        folder_name = sanitize_url_to_folder(profile_url)
        report_root = ROOT / folder_name
        report_root.mkdir(parents=True, exist_ok=True)
        
        # Snapshots go into a subfolder
        snapshot_dir = report_root / "snapshots"
        snapshot_dir.mkdir(exist_ok=True)
        # ---------------- Task Definitions ----------------
        tasks = []
        
        # Task 1: Main Profile
        tasks.append({
            "key": "profile_main",
            "url": profile_url,
            "scroll": 10
        })

        # Task 2: About Subsections
        about_subsections = [
            ("about_intro", "about"),
            ("about_work", "directory_work"), 
            ("about_education", "directory_education"),
            ("about_personal_details", "directory_personal_details")
        ]
        for key, sk_val in about_subsections:
            # User requested main about section to scroll till end. Others no scroll.
            s_rounds = 25 if key == "about_intro" else 0
            tasks.append({
                "key": key,
                "url": construct_section_url(base_profile_url, sk_val),
                "scroll": s_rounds
            })

        # Task 3: Friends
        tasks.append({
            "key": "friends",
            "url": construct_section_url(base_profile_url, "friends"),
            "scroll": MAX_FRIEND_SCROLLS
        })

        # Task 4: Photos Grid
        tasks.append({
            "key": "photos_grid",
            "url": construct_section_url(base_profile_url, "photos_by"),
            "scroll": 25
        })

        # Task 5: Videos
        tasks.append({
            "key": "videos",
            "url": construct_section_url(base_profile_url, "videos"),
            "scroll": 25
        })

        # Task 6: Reels
        tasks.append({
            "key": "reels",
            "url": construct_section_url(base_profile_url, "reels"),
            "scroll": 25
        })
        
        # ---------------- Pipeline Execution ----------------
        pending_captures = []

        def check_and_collect_pending(force_wait=False):
            active_list = []
            for item in pending_captures:
                p = item['page']
                key = item['key']
                
                try:
                    res = collect_singlefile_result(p, key)
                    if res:
                        save_snapshot_content(res, snapshot_dir, profile_id, key)
                        if p != first_page: # Don't close the main first page until very end? Or just close it.
                            try: p.close()
                            except: pass
                        continue
                    else:
                        if force_wait:
                            logger.info("Waiting for background capture: %s", key)
                            try:
                                p.wait_for_function(f"() => window.__singlefile_results && window.__singlefile_results['{key}'] !== undefined", timeout=SINGLEFILE_TIMEOUT_MS)
                                res = collect_singlefile_result(p, key)
                                save_snapshot_content(res, snapshot_dir, profile_id, key)
                            except Exception as e:
                                logger.error("Failed waiting for %s: %s", key, e)
                            if p != first_page:
                                try: p.close()
                                except: pass
                            continue
                        else:
                            active_list.append(item)
                except Exception as e:
                    logger.error("Error checking %s: %s", key, e)
                    try: p.close() 
                    except: pass
            
            pending_captures[:] = active_list

        
        # Iterate Tasks
        for i, task in enumerate(tasks):
            t_key = task['key']
            t_url = task['url']
            t_scroll = task['scroll']
            
            logger.info("=== Processing Task %d/%d: %s ===", i+1, len(tasks), t_key)
            
            if i == 0:
                page = first_page
            else:
                page = context.new_page()
            
            try:
                logger.info("Navigating %s...", t_url)
                page.goto(t_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(WAIT_AFTER_NAV)
                
                if t_key == "profile_main":
                    wait_for_page_stable(page)
                    logger.info("Scrolling...")
                    auto_scroll_page(page, max_rounds=t_scroll, step_callback=lambda: check_and_collect_pending(force_wait=False))
                    try:
                        page.keyboard.press("Escape")
                        time.sleep(0.5)
                        page.keyboard.press("Escape")
                    except: pass
                else:
                    wait_for_page_stable(page)
                    if t_scroll > 0:
                        logger.info("Scrolling...")
                        auto_scroll_page(page, max_rounds=t_scroll, step_callback=lambda: check_and_collect_pending(force_wait=False))
                
                logger.info("Triggering capture for %s...", t_key)
                trigger_singlefile_capture(page, t_key)
                
                pending_captures.append({"page": page, "key": t_key, "start_time": time.time()})
                
                # Maintenance
                check_and_collect_pending(force_wait=False)
                
            except Exception as e:
                logger.error("Task %s failed: %s", t_key, e)
                try: page.close()
                except: pass

        logger.info("All tasks initiated. Waiting for remaining %d captures...", len(pending_captures))
        check_and_collect_pending(force_wait=True)


        # create master index
        logger.info("Creating master index HTML")
        snapshots = sorted([p for p in snapshot_dir.iterdir() if p.is_file() and p.suffix == ".html"])
        master_path = report_root / "index.html"
        
        # Categorize snapshots
        categories = {
            "Main Profile": [],
            "About & Info": [],
            "Friends": [],
            "Photos": [],
            "Videos": [],
            "Likes, Check-ins, Events": [],
            "Other": []
        }
        
        for s in snapshots:
            name = s.name.lower()
            if "profile_main" in name:
                categories["Main Profile"].append(s)
            elif "about" in name:
                categories["About & Info"].append(s)
            elif "friends" in name:
                categories["Friends"].append(s)
            elif "photo" in name:
                categories["Photos"].append(s)
            elif "video" in name or "reels" in name:
                categories["Videos"].append(s)
            else:
                categories["Other"].append(s)
        
        with open(master_path, "w", encoding="utf-8") as mf:
            mf.write("<!doctype html>\n<html>\n<head>\n<meta charset='utf-8'>\n")
            mf.write(f"<title>Facebook export {profile_id}</title>\n")
            mf.write("<style>body{font-family:Arial,Helvetica,sans-serif;margin:20px;line-height:1.6} h1{color:#1877f2} h2{border-bottom:1px solid #ccc;padding-bottom:5px;margin-top:30px} a{text-decoration:none;color:#333;font-size:16px} a:hover{color:#1877f2;text-decoration:underline} ul{list-style-type:none;padding:0} li{margin:8px 0}</style>\n")
            mf.write("</head>\n<body>\n")
            mf.write(f"<h1>Export for profile {profile_id}</h1>\n")
            mf.write(f"<div>Source: <a href='{profile_url}' target='_blank'>{profile_url}</a></div>\n")
            
            for cat_name, items in categories.items():
                if not items: continue
                mf.write(f"<h2>{cat_name}</h2>\n<ul>\n")
                for s in items:
                    rel = f"snapshots/{s.name}"
                    label = s.name.replace(".html", "").replace("_", " ").title()
                    mf.write(f"<li><a href='{rel}' target='_blank'>📄 {label}</a></li>\n")
                mf.write("</ul>\n")
                
            mf.write("</body>\n</html>\n")
        logger.info("Master index created at %s", master_path)

        # close context
        try:
            context.close()
        except:
            pass
            
        if REMOVE_TEMP_AT_END:
            try:
                shutil.rmtree(EXT_DIR, ignore_errors=True)
                shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
            except:
                pass

if __name__ == "__main__":
    url = input("Facebook Profile URL: ").strip()
    if url:
        run(url)
