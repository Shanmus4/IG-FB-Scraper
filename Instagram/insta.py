#!/usr/bin/env python3
# insta_report_embed.py
# Requires: requests, python-dotenv
# pip install requests python-dotenv

import os
import re
import sys
import json
import time
import base64
import random
import html
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# ---------------- CONFIG ----------------
# Defaults removed from CLI; values are no longer used

# Limits
MAX_FOLLOWS = 400
PAGE_SIZE_FOLLOWS = 50
MAX_POSTS = 1000000  # effectively no max
MAX_TAGGED = 1000000  # effectively no max
MAX_LIKES_PER_POST = 1000000  # effectively no max
PAGE_SIZE_LIKES = 50
MAX_COMMENTS_PER_POST = 1000000  # effectively no max
PAGE_SIZE_COMMENTS = 50

# Timing to reduce rate-limit risk
SLEEP_MIN = 0.7
SLEEP_MAX = 1.5

# IG web constants
X_IG_APP_ID = "936619743392459"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Common query_hash values (these may change over time)
HASH_FOLLOWERS = "c76146de99bb02f6415203be841dd25a"
HASH_FOLLOWING = "d04b0a864b4b54837c0d870b0e77e076"
HASH_LIKES = "d5d763b1e2acf209d62d22d184488e57"
HASH_COMMENTS = "bc3296d1ce80a24b1b6e40b1e72903f5"
HASH_TAGGED = "ff260833edf142911047af6024eb634a"

URL_GRAPHQL = "https://www.instagram.com/graphql/query/"
URL_WEB_PROFILE_INFO = "https://www.instagram.com/api/v1/users/web_profile_info/"

# ---------------- Helpers ----------------

def sanitize_filename(name: str) -> str:
    """Sanitize a filename for Windows by replacing illegal characters."""
    try:
        return re.sub(r'[\\/:*?"<>|]+', '_', (name or '').strip())
    except Exception:
        return "output"

def rnd_sleep():
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

def safe_json_response(resp: requests.Response) -> Dict[str, Any]:
    ct = resp.headers.get("content-type","")
    text_head = resp.text[:200]
    if "application/json" not in ct:
        raise RuntimeError(f"Expected JSON response but got content-type={ct} status={resp.status_code}. Body head={text_head!r}")
    return resp.json()

def normalize_username(input_str: str) -> str:
    """Accepts either a username or a full Instagram profile URL and returns the username.
    Examples:
      - "https://www.instagram.com/someuser/" -> "someuser"
      - "someuser" -> "someuser"
    """
    s = input_str.strip()
    if not s:
        return s
    if s.startswith("http://") or s.startswith("https://"):
        try:
            parsed = urllib.parse.urlparse(s)
            path = parsed.path or ""
            # strip leading/trailing slashes
            path = path.strip("/")
            if not path:
                return ""
            # username should be the first segment
            seg = path.split("/")[0]
            # guard against non-profile paths like p/, reel/, stories/
            if seg.lower() in {"p","reel","reels","stories","explore"}:
                # Not a profile URL; no username derivable
                return ""
            return seg
        except Exception:
            return ""
    # looks like a plain username
    return s

def build_session(cookie_str: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": DEFAULT_UA,
        "X-IG-App-ID": X_IG_APP_ID,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
        "Origin": "https://www.instagram.com",
    })
    # Put cookie header exact
    s.headers["Cookie"] = cookie_str
    # Add CSRF header if present in cookie; some web API endpoints require it
    try:
        m = re.search(r"csrftoken=([^;]+)", cookie_str)
        if m:
            s.headers["X-CSRFToken"] = m.group(1)
        # X-IG-WWW-Claim also improves success on web API endpoints
        m2 = re.search(r"ig_www_claim=([^;]+)", cookie_str)
        if m2:
            s.headers["X-IG-WWW-Claim"] = m2.group(1)
        # Intended user headers often required by web API
        m3 = re.search(r"ds_user_id=([^;]+)", cookie_str)
        if m3:
            dsid = m3.group(1)
            s.headers["IG-U-DS-USER-ID"] = dsid
            s.headers["IG-INTENDED-USER-ID"] = dsid
    except Exception:
        pass
    # Some endpoints behave better with XMLHttpRequest header
    s.headers["X-Requested-With"] = "XMLHttpRequest"
    # Common header present in web app requests; value can vary, this default often works
    s.headers["X-ASBD-ID"] = "129477"
    return s

def get_json(session: requests.Session, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    resp = session.get(url, params=params, timeout=30)
    return safe_json_response(resp)

def download_and_base64(session: requests.Session, url: str, referer: Optional[str] = None) -> str:
    # Fetch image/binary and return data:image/...;base64,... with robust headers and retries
    hdrs = {
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Cache-Control": "no-cache",
    }
    if referer:
        hdrs["Referer"] = referer
    try:
        resp = session.get(url, timeout=30, stream=True, headers=hdrs, allow_redirects=True)
    except Exception:
        return ""
    if resp.status_code != 200 or not resp.headers.get("content-type","").startswith("image/"):
        # retry once with generic instagram referer if not already used
        if not referer:
            try:
                resp = session.get(url, timeout=30, stream=True, headers={**hdrs, "Referer": "https://www.instagram.com/"}, allow_redirects=True)
            except Exception:
                return ""
        # if still bad, give up
    if resp.status_code != 200:
        return ""
    content_type = resp.headers.get("content-type","image/jpeg")
    try:
        data = resp.content
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{content_type};base64,{b64}"
    except Exception:
        return ""

def linkify(text: str) -> Tuple[str, List[str], List[str]]:
    # Replace @mentions and #hashtags with anchor links for HTML output.
    if not text:
        return "", [], []
    mentions = re.findall(r"@([A-Za-z0-9._]+)", text)
    hashtags = re.findall(r"#(\w+)", text)
    safe = html.escape(text)
    # replace mentions and hashtags using regex on the escaped string
    def repl_mention(m):
        u = m.group(1)
        return f'<a href="https://www.instagram.com/{html.escape(u)}/">@{html.escape(u)}</a>'
    def repl_hashtag(m):
        tag = m.group(1)
        return f'<a href="https://www.instagram.com/explore/tags/{html.escape(tag)}/">#{html.escape(tag)}</a>'
    safe = re.sub(r"@([A-Za-z0-9._]+)", repl_mention, safe)
    safe = re.sub(r"#(\w+)", repl_hashtag, safe)
    return safe, mentions, hashtags

def human_time(ts: Optional[int]) -> str:
    if not ts:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except:
        return str(ts)

# ---------------- Data fetch functions ----------------

def fetch_profile_info(session: requests.Session, username: str) -> Dict[str, Any]:
    """Fetch profile via web_profile_info; if missing or timeline edges empty, fallback to ?__a=1."""
    params = {"username": username}
    try:
        data = get_json(session, URL_WEB_PROFILE_INFO, params)
        user = data.get("data", {}).get("user")
    except Exception:
        user = None
    # If user missing or timeline edges empty, try alt endpoint
    if not user or not (user.get("edge_owner_to_timeline_media", {}).get("edges")):
        alt_url = f"https://www.instagram.com/{username}/"
        try:
            alt_resp = session.get(alt_url, params={"__a": "1", "__d": "dis"}, headers={"Referer": alt_url}, timeout=30)
            if "application/json" in alt_resp.headers.get("content-type", ""):
                alt = alt_resp.json()
                alt_user = (
                    alt.get("graphql", {}).get("user")
                    or alt.get("user")
                    or alt.get("data", {}).get("user")
                )
                if alt_user:
                    user = alt_user
        except Exception:
            pass
    if not user:
        raise RuntimeError("Profile info not found from either endpoint.")
    return user

def paginate_follow(session: requests.Session, user_id: str, follow_type: str, limit: int) -> List[Dict[str, Any]]:
    """
    follow_type: 'followers' or 'following'
    """
    assert follow_type in ("followers", "following")
    hash_id = HASH_FOLLOWERS if follow_type == "followers" else HASH_FOLLOWING
    nodes: List[Dict[str, Any]] = []
    after = None
    first = min(PAGE_SIZE_FOLLOWS, limit)
    while len(nodes) < limit:
        variables = {"id": str(user_id), "include_reel": True, "fetch_mutual": False, "first": first}
        if after:
            variables["after"] = after
        params = {"query_hash": hash_id, "variables": json.dumps(variables, separators=(',',':'))}
        data = get_json(session, URL_GRAPHQL, params)
        user = data.get("data", {}).get("user", {})
        key = "edge_followed_by" if follow_type == "followers" else "edge_follow"
        block = user.get(key, {})
        edges = block.get("edges", [])
        for e in edges:
            node = e.get("node")
            if node:
                nodes.append(node)
            if len(nodes) >= limit:
                break
        page_info = block.get("page_info", {})
        if not page_info.get("has_next_page"):
            break
        after = page_info.get("end_cursor")
        if not after:
            break
        rnd_sleep()
    return nodes

def fetch_timeline_via_feed(session: requests.Session, user_id: str, limit: int) -> List[Dict[str, Any]]:
    """Fallback: fetch timeline items from the web API feed and map to node-like dicts.
    Some items may not have 'shortcode'; in that case we will skip likes/comments fetching for those items.
    """
    collected: List[Dict[str, Any]] = []
    count = min(50, max(1, limit))
    max_id: Optional[str] = None
    base_url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/"
    while len(collected) < limit:
        params = {"count": str(count)}
        if max_id:
            params["max_id"] = max_id
        try:
            data = get_json(session, base_url, params)
        except Exception as e:
            print(f"[WARN] feed user fallback failed: {e}")
            break
        items = data.get("items") or []
        for it in items:
            # Map to a node-like shape used by HTML builder
            shortcode = it.get("code") or it.get("shortcode") or ""
            # Media identifiers
            # Prefer the composite media id string (often like "<pk>_<ownerid>") for web API endpoints.
            media_pk = it.get("pk")
            media_id_str = it.get("id") or ""
            if not media_pk and media_id_str:
                m = re.match(r"(\d+)", str(media_id_str))
                if m:
                    media_pk = m.group(1)
            # image url
            disp = ""
            iv2 = it.get("image_versions2") or {}
            cands = iv2.get("candidates") or []
            if cands:
                disp = (cands[-1] or {}).get("url", "")
            if not disp:
                disp = it.get("thumbnail_url") or ""
            # caption
            cap = (it.get("caption") or {}).get("text", "")
            like_count = it.get("like_count") or 0
            comment_count = it.get("comment_count") or 0
            taken_at = it.get("taken_at")
            product_type = it.get("product_type") or ""
            # heuristic for reels
            if not product_type and it.get("media_type") == 2:
                if it.get("clips_metadata") or it.get("music_metadata"):
                    product_type = "clips"
            node = {
                "shortcode": shortcode,
                # Use composite media id string when available; fallback to numeric pk
                "media_id": (media_id_str or media_pk or ""),
                "media_pk": media_pk or "",
                "display_url": disp,
                "taken_at_timestamp": taken_at,
                "product_type": product_type,
                "edge_liked_by": {"count": like_count},
                "edge_media_to_comment": {"count": comment_count},
                "edge_media_to_caption": {"edges": [{"node": {"text": cap}}]},
            }
            collected.append(node)
            if len(collected) >= limit:
                break
        max_id = data.get("next_max_id")
        if not max_id:
            break
        rnd_sleep()
    return collected

def fetch_likers_by_media_id(session: requests.Session, media_id: str, limit: int, referer: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fallback: fetch likers using media ID.
    Endpoint: /api/v1/media/{media_id}/likers/
    Sends a post-specific Referer to improve success rate.
    """
    if not media_id:
        return []
    url = f"https://www.instagram.com/api/v1/media/{media_id}/likers/"
    params = {"count": str(min(200, max(1, limit)))}
    try:
        if referer:
            resp = session.get(url, params=params, headers={"Referer": referer}, timeout=30)
            data = safe_json_response(resp)
        else:
            data = get_json(session, url, params)
    except Exception as e:
        print(f"[WARN] media likers fallback failed: {e}")
        return []
    # Instagram may return different shapes; normalize generously
    raw_list = data.get("users") or data.get("likers") or data.get("items") or []
    out: List[Dict[str, Any]] = []
    for u in raw_list:
        if len(out) >= limit:
            break
        # Some responses nest the user object under 'user'
        cand = u.get("user") if isinstance(u, dict) else None
        obj = cand if isinstance(cand, dict) else (u if isinstance(u, dict) else {})
        username = obj.get("username") or ""
        full_name = obj.get("full_name") or obj.get("fullName") or ""
        if username:
            out.append({"username": username, "full_name": full_name})
    return out

def fetch_comments_by_media_id(session: requests.Session, media_id: str, limit: int) -> List[Dict[str, Any]]:
    """Fallback: fetch comments using media ID with pagination.
    Endpoint: /api/v1/media/{media_id}/comments/
    """
    if not media_id:
        return []
    url = f"https://www.instagram.com/api/v1/media/{media_id}/comments/"
    out: List[Dict[str, Any]] = []
    max_id: Optional[str] = None
    while len(out) < limit:
        params: Dict[str, Any] = {}
        if max_id:
            params["max_id"] = max_id
        try:
            data = get_json(session, url, params)
        except Exception as e:
            print(f"[WARN] media comments fallback failed: {e}")
            break
        comments = data.get("comments") or []
        for c in comments:
            # Normalize to GraphQL-like node for HTML
            out.append({
                "text": c.get("text",""),
                "created_at": c.get("created_at"),
                "owner": {"username": (c.get("user") or {}).get("username","")},
            })
            if len(out) >= limit:
                break
        max_id = data.get("next_max_id")
        if not max_id:
            break
        rnd_sleep()
    return out

def fetch_post_likes(session: requests.Session, shortcode: str, limit: int) -> List[Dict[str, Any]]:
    nodes = []
    after = None
    first = min(PAGE_SIZE_LIKES, limit)
    while len(nodes) < limit:
        variables = {"shortcode": shortcode, "include_reel": True, "first": first}
        if after:
            variables["after"] = after
        params = {"query_hash": HASH_LIKES, "variables": json.dumps(variables, separators=(',',':'))}
        data = get_json(session, URL_GRAPHQL, params)
        edge = data.get("data", {}).get("shortcode_media", {}).get("edge_liked_by", {})
        edges = edge.get("edges", [])
        for e in edges:
            node = e.get("node")
            if node:
                nodes.append(node)
            if len(nodes) >= limit:
                break
        page_info = edge.get("page_info", {})
        if not page_info.get("has_next_page"):
            break
        after = page_info.get("end_cursor")
        if not after:
            break
        rnd_sleep()
    return nodes

def fetch_post_comments(session: requests.Session, shortcode: str, limit: int) -> List[Dict[str, Any]]:
    nodes = []
    after = None
    first = min(PAGE_SIZE_COMMENTS, limit)
    while len(nodes) < limit:
        variables = {"shortcode": shortcode, "first": first}
        if after:
            variables["after"] = after
        params = {"query_hash": HASH_COMMENTS, "variables": json.dumps(variables, separators=(',',':'))}
        data = get_json(session, URL_GRAPHQL, params)
        edge = data.get("data", {}).get("shortcode_media", {}).get("edge_media_to_comment", {})
        edges = edge.get("edges", [])
        for e in edges:
            node = e.get("node")
            if node:
                nodes.append(node)
            if len(nodes) >= limit:
                break
        page_info = edge.get("page_info", {})
        if not page_info.get("has_next_page"):
            break
        after = page_info.get("end_cursor")
        if not after:
            break
        rnd_sleep()
    return nodes

def fetch_tagged(session: requests.Session, user_id: str, limit: int) -> List[Dict[str, Any]]:
    nodes = []
    after = None
    first = min(24, limit)
    while len(nodes) < limit:
        variables = {"id": str(user_id), "first": first}
        if after:
            variables["after"] = after
        params = {"query_hash": HASH_TAGGED, "variables": json.dumps(variables, separators=(',',':'))}
        data = get_json(session, URL_GRAPHQL, params)
        media = data.get("data", {}).get("user", {}).get("edge_user_to_photos_of_you", {})
        edges = media.get("edges", [])
        for e in edges:
            node = e.get("node")
            if node:
                nodes.append(node)
            if len(nodes) >= limit:
                break
        page_info = media.get("page_info", {})
        if not page_info.get("has_next_page"):
            break
        after = page_info.get("end_cursor")
        if not after:
            break
        rnd_sleep()
    return nodes

# ---------------- Build HTML with embedded images ----------------

def build_html_report(out_path: str, username: str, user_id: str, profile: Dict[str, Any],
                      followers: List[Dict[str,Any]], following: List[Dict[str,Any]],
                      posts: List[Dict[str,Any]], reels: List[Dict[str,Any]], tagged: List[Dict[str,Any]]):
    esc = html.escape
    p = profile
    def user_link(u):
        if not u:
            return ""
        return f'<a href="https://www.instagram.com/{esc(u)}/">@{esc(u)}</a>'

    def followers_html(lst):
        return "\n".join(f'<li>{user_link(n.get("username"))} <span class="muted">{esc(n.get("full_name",""))}</span></li>' for n in lst)

    def comments_html(comments):
        out=[]
        for c in comments:
            owner = c.get("owner",{})
            username = owner.get("username","")
            text = c.get("text","")
            ts = human_time(c.get("created_at"))
            out.append(f'<li>{user_link(username)}: {esc(text)} <span class="muted">{esc(ts)}</span></li>')
        return "\n".join(out)

    def likes_html(likes):
        return "\n".join(f'<li>{user_link(n.get("username",""))}</li>' for n in likes)

    def post_card(n, idx: int, kind: str = "Post"):
        shortcode = n.get("shortcode","")
        url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else "#"
        ts = human_time(n.get("taken_at_timestamp"))
        # caption
        caption = ""
        edges = n.get("edge_media_to_caption",{}).get("edges",[])
        if edges:
            caption = edges[0].get("node",{}).get("text","")
        caption_html, mentions, hashtags = linkify(caption)
        # embedded primary image if available
        media_uri = ""
        # Prefer full display_url; fallbacks for nodes that only expose thumbnails
        if n.get("display_url"):
            media_uri = n.get("display_url")
        elif n.get("thumbnail_src"):
            media_uri = n.get("thumbnail_src")
        else:
            # try display_resources then thumbnail_resources
            dr = n.get("display_resources") or []
            if dr:
                media_uri = (dr[-1] or {}).get("src","")
            if not media_uri:
                tr = n.get("thumbnail_resources") or []
                if tr:
                    media_uri = (tr[-1] or {}).get("src","")
        # if _embedded_media exists already (we set earlier), use it
        embedded = n.get("_embedded_media_b64") or ""
        # likes/comments (fetched earlier)
        likes_nodes = n.get("_likes",[])
        comments_nodes = n.get("_comments",[])
        # build html
        title = f"{kind} {idx}"
        out = [f'<div class="card"><div class="meta"><a href="{esc(url)}">{esc(title)}</a></div>',
               f'<div class="muted">{esc(ts)}</div>']
        if embedded:
            out.append(f'<img class="media" src="{embedded}" alt="post media">')
        elif media_uri:
            out.append(f'<img class="media" src="{esc(media_uri)}" alt="post media (url)">')
        chips_html = " ".join(
            f'<a class="chip" href="https://www.instagram.com/{html.escape(m)}/">@{html.escape(m)}</a>'
            for m in mentions
        )
        out.append(f'<div class="chips">{chips_html}</div>')
        out.append(f'<div><strong>Caption</strong><br><pre>{caption_html}</pre></div>')
        out.append(f'<div class="kpis"><div class="kpi">Likes: {esc(str(n.get("edge_liked_by",{}).get("count","")))}</div><div class="kpi">Comments: {esc(str(n.get("edge_media_to_comment",{}).get("count","")))}</div></div>')
        out.append(f'<details><summary>Likes (up to {MAX_LIKES_PER_POST}) — {len(likes_nodes)}</summary><div class="content"><ul class="list">{likes_html(likes_nodes)}</ul></div></details>')
        out.append(f'<details><summary>Comments (up to {MAX_COMMENTS_PER_POST}) — {len(comments_nodes)}</summary><div class="content"><ul class="list">{comments_html(comments_nodes)}</ul></div></details>')
        out.append("</div>")
        return "\n".join(out)

    # Build HTML
    html_doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Instagram Report - {esc(username)}</title>
    <style>
    body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:20px;background:#0b0c10;color:#e6edf3}}
    a{{color:#6ab7ff;text-decoration:none}} a:hover{{text-decoration:underline}}
    .muted{{color:#9aa4b2;font-size:0.9em}}
    .header{{display:flex;gap:16px;align-items:center}}
    .avatar{{width:100px;height:100px;border-radius:50%;object-fit:cover;border:2px solid #1f6feb}}
    .kpis{{display:flex;gap:12px;margin:8px 0}}
    .kpi{{background:#111827;padding:6px 10px;border-radius:10px;border:1px solid #1f2937}}
    .section{{margin:28px 0}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
    .card{{background:#0e1117;border:1px solid #1f2937;border-radius:12px;padding:12px}}
    .media{{width:100%;border-radius:8px;display:block;margin-bottom:8px}}
    .list{{list-style:none;padding:0;margin:0}}
    .list li{{padding:6px 0;border-bottom:1px solid #1f2937}}
    .chips .chip{{margin-right:6px}}
    details{{background:#0e1117;border:1px solid #1f2937;border-radius:10px;margin:8px 0}}
    details > summary{{cursor:pointer;padding:10px;font-weight:600;list-style:none;display:block}}
    details > summary::after{{content:'▸'; float:right; color:#9aa4b2;}}
    details[open] > summary{{border-bottom:1px solid #1f2937}}
    details[open] > summary::after{{content:'▾'}}
    details .content{{padding:10px;overflow:auto}}
    pre{{white-space:pre-wrap}}
    </style>
    </head><body>
    <h1>Instagram Report - {esc(username)}</h1>
    <div class="section header">
    """

    # Profile avatar embedded?
    profile_pic_uri = ""
    if profile.get("profile_pic_url_hd"):
        profile_pic_uri = profile.get("profile_pic_url_hd")
    elif profile.get("profile_pic_url"):
        profile_pic_uri = profile.get("profile_pic_url")
    profile_emb = profile.get("_embedded_profile_pic_b64") or ""
    if profile_emb:
        html_doc += f'<img class="avatar" src="{profile_emb}" alt="avatar">'
    elif profile_pic_uri:
        html_doc += f'<img class="avatar" src="{html.escape(profile_pic_uri)}" alt="avatar">'
    html_doc += f'<div><h2><a href="https://www.instagram.com/{esc(username)}/">@{esc(username)}</a></h2>'
    html_doc += f'<div class="muted">Profile ID: {esc(user_id)}</div>'
    html_doc += f'<div class="kpis"><div class="kpi">Posts: {esc(str(profile.get("edge_owner_to_timeline_media",{}).get("count","")) )}</div><div class="kpi">Followers: {esc(str(profile.get("edge_followed_by",{}).get("count","")))}</div><div class="kpi">Following: {esc(str(profile.get("edge_follow",{}).get("count","")))}</div></div>'
    html_doc += f'<div><strong>Full name</strong>: {esc(profile.get("full_name",""))}</div>'
    # Bio: linkify mentions/hashtags and URLs; also include bio_links if present
    bio_text = profile.get("biography", "") or ""
    # Linkify mentions/hashtags first
    bio_linkified, _m, _h = linkify(bio_text)
    # Linkify raw URLs
    url_pattern = re.compile(r"(https?://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+)")
    bio_linkified = url_pattern.sub(lambda m: f'<a href="{html.escape(m.group(1))}">{html.escape(m.group(1))}</a>', bio_linkified)
    html_doc += f'<div><strong>Bio</strong><br><pre>{bio_linkified}</pre></div>'
    # Render bio_links if API exposes them
    bio_links = profile.get("bio_links") or []
    if isinstance(bio_links, list) and bio_links:
        links_html = []
        for bl in bio_links:
            u = (bl or {}).get("url") or (bl or {}).get("link_url")
            if u:
                links_html.append(f'<a class="chip" href="{html.escape(u)}">{html.escape(u)}</a>')
        if links_html:
            html_doc += f'<div class="chips">' + " ".join(links_html) + '</div>'
    # Facebook profile biolink if present
    fb_link = profile.get("fb_profile_biolink")
    fb_url = None
    if isinstance(fb_link, dict):
        fb_url = fb_link.get("link_url") or fb_link.get("url")
    elif isinstance(fb_link, str):
        fb_url = fb_link
    if fb_url:
        html_doc += f'<div class="chips"><span class="muted">Facebook:</span> <a class="chip" href="{html.escape(fb_url)}">{html.escape(fb_url)}</a></div>'
    if profile.get("external_url"):
        html_doc += f'<div><strong>External URL</strong>: <a href="{esc(profile.get("external_url"))}">{esc(profile.get("external_url"))}</a></div>'
    html_doc += '</div></div>'

    # Followers
    html_doc += '<div class="section">'
    html_doc += f'<details><summary>Followers (up to {MAX_FOLLOWS}) — {len(followers)}</summary><div class="content"><ul class="list">{followers_html(followers)}</ul></div></details>'
    html_doc += '</div>'

    # Following
    html_doc += '<div class="section">'
    html_doc += f'<details><summary>Following (up to {MAX_FOLLOWS}) — {len(following)}</summary><div class="content"><ul class="list">{followers_html(following)}</ul></div></details>'
    html_doc += '</div>'

    # Posts
    html_doc += '<div class="section"><h3>Posts (most recent)</h3><div class="grid">%s</div></div>' % ("\n".join(post_card(n, i, "Post") for i, n in enumerate(posts, start=1)))

    # Reels
    html_doc += '<div class="section"><h3>Reels (from timeline)</h3><div class="grid">%s</div></div>' % ("\n".join(post_card(n, i, "Reel") for i, n in enumerate(reels, start=1)))

    # Tagged
    html_doc += '<div class="section"><h3>Tagged</h3><div class="grid">%s</div></div>' % ("\n".join(post_card(n, i, "Tagged") for i, n in enumerate(tagged, start=1)))

    html_doc += "</body></html>"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"[i] HTML report saved to {os.path.abspath(out_path)}")

# ---------------- Main orchestration ----------------

def main():
    # Load .env from the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    load_dotenv(env_path)
    
    cookie_val = os.getenv("INSTAGRAM_COOKIE")
    if not cookie_val:
        # Fallback: allow .env to contain just the raw cookie string
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if raw:
                if raw.startswith("INSTAGRAM_COOKIE="):
                    cookie_val = raw.split("=", 1)[1].strip()
                else:
                    cookie_val = raw
        except Exception as e:
            print(f"[ERROR] Could not read .env file: {e}")
            cookie_val = None
    if not cookie_val:
        print("[ERROR] Instagram cookie not found. Put your full Cookie header in .env (either as raw content or INSTAGRAM_COOKIE=...)")
        sys.exit(1)

    print("=== Instagram Full Harvester (embedded images) ===")
    profile_input = input("Profile URL or username: ").strip()
    if not profile_input:
        print("[ERROR] A profile URL or username is required.")
        sys.exit(1)

    session = build_session(cookie_val)

    # 1) fetch profile info
    username = normalize_username(profile_input) or profile_input
    print(f"[i] Fetching profile info for {username} ...")
    try:
        profile = fetch_profile_info(session, username)
    except Exception as e:
        print("[ERROR] Failed to fetch profile info:", e)
        sys.exit(1)

    # Auto-derive user_id from profile
    user_id = profile.get("id") or profile.get("pk") or ""
    if not user_id:
        print("[WARN] Could not auto-detect user_id; some endpoints may not work.")

    # Auto output filename based on username: "<username> | Insta.html" (Windows-safe)
    out_html = sanitize_filename(f"{username} | Insta") + ".html"

    # Try to embed profile pic
    profile_pic_url = profile.get("profile_pic_url_hd") or profile.get("profile_pic_url")
    if profile_pic_url:
        emb = download_and_base64(session, profile_pic_url)
        if emb:
            profile["_embedded_profile_pic_b64"] = emb
        rnd_sleep()

    # 2) followers / following
    print(f"[i] Fetching up to {MAX_FOLLOWS} followers ...")
    followers_nodes = paginate_follow(session, user_id, "followers", MAX_FOLLOWS)
    followers = [{"username": n.get("username",""), "full_name": n.get("full_name","")} for n in followers_nodes]

    print(f"[i] Fetching up to {MAX_FOLLOWS} following ...")
    following_nodes = paginate_follow(session, user_id, "following", MAX_FOLLOWS)
    following = [{"username": n.get("username",""), "full_name": n.get("full_name","")} for n in following_nodes]

    # 3) posts from profile info timeline (fallback was already attempted in fetch_profile_info)
    timeline_block = profile.get("edge_owner_to_timeline_media",{})
    timeline = timeline_block.get("edges",[])[:MAX_POSTS]
    timeline_nodes = [e.get("node",{}) for e in timeline if e.get("node")]
    if not timeline_nodes:
        count_val = timeline_block.get("count")
        print("[i] Timeline empty in profile JSON. Using feed fallback if available ...")
        try:
            if (count_val or 0) > 0:
                timeline_nodes = fetch_timeline_via_feed(session, user_id, MAX_POSTS)
        except Exception:
            pass
    posts = []
    reels = []
    print(f"[i] Processing up to {len(timeline_nodes)} timeline posts for likes/comments and embedding media ...")
    for idx, node in enumerate(timeline_nodes, start=1):
        shortcode = node.get("shortcode")
        # fetch likes/comments via GraphQL when possible; else fallback to media-id endpoints
        likes_nodes = []
        comments_nodes = []
        print(f"[i] Post {idx}: extracting likes and comments ...")
        if shortcode:
            try:
                likes_nodes = fetch_post_likes(session, shortcode, MAX_LIKES_PER_POST)
            except Exception:
                likes_nodes = []
            try:
                comments_nodes = fetch_post_comments(session, shortcode, MAX_COMMENTS_PER_POST)
            except Exception:
                comments_nodes = []
        # fallback via media id if available and lists are empty
        if (not likes_nodes or not comments_nodes) and node.get("media_id"):
            mid = str(node.get("media_id"))
            referer_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else "https://www.instagram.com/"
            likes_nodes2 = []
            comments_nodes2 = []
            try:
                likes_nodes2 = fetch_likers_by_media_id(session, mid, MAX_LIKES_PER_POST, referer=referer_url)
            except Exception:
                likes_nodes2 = []
            try:
                comments_nodes2 = fetch_comments_by_media_id(session, mid, MAX_COMMENTS_PER_POST)
            except Exception:
                comments_nodes2 = []
            if likes_nodes2 and not likes_nodes:
                likes_nodes = likes_nodes2
            if comments_nodes2 and not comments_nodes:
                comments_nodes = comments_nodes2
        # embed primary image (display_url) as base64
        media_src = node.get("display_url") or ""
        embedded_media = ""
        if media_src:
            # attempt with post referer if shortcode available (improves success on some CDNs)
            ref = f"https://www.instagram.com/p/{shortcode}/" if shortcode else None
            embedded_media = download_and_base64(session, media_src, referer=ref)
        node["_embedded_media_b64"] = embedded_media
        # store fetched nodes in node
        node["_likes"] = [{"username": ln.get("username","")} for ln in likes_nodes if ln.get("username")]
        node["_comments"] = comments_nodes
        if node.get("product_type") == "clips":
            reels.append(node)
        else:
            posts.append(node)

    # 4) tagged posts
    tagged_nodes = fetch_tagged(session, user_id, MAX_TAGGED)
    tagged = []
    for idx, n in enumerate(tagged_nodes[:MAX_TAGGED], start=1):
        # fetch likes/comments for tagged when shortcode exists
        sc = n.get("shortcode")
        # collect best candidate URLs (tagged often only has thumbs/sidecar)
        candidates = []
        def add(x):
            if x and x not in candidates:
                candidates.append(x)
        add(n.get("display_url"))
        add(n.get("thumbnail_src"))
        for r in (n.get("display_resources") or [])[::-1]:
            add((r or {}).get("src"))
        for r in (n.get("thumbnail_resources") or [])[::-1]:
            add((r or {}).get("src"))
        side = n.get("edge_sidecar_to_children", {}).get("edges", [])
        if side:
            child = (side[0] or {}).get("node", {})
            add(child.get("display_url"))
            add(child.get("thumbnail_src"))
            for r in (child.get("display_resources") or [])[::-1]:
                add((r or {}).get("src"))
            for r in (child.get("thumbnail_resources") or [])[::-1]:
                add((r or {}).get("src"))
        # try to embed using candidates
        emb = ""
        ref = f"https://www.instagram.com/p/{sc}/" if sc else "https://www.instagram.com/"
        for u in candidates:
            if not u:
                continue
            emb = download_and_base64(session, u, referer=ref)
            if not emb:
                emb = download_and_base64(session, u)
            if emb:
                n["_embedded_media_b64"] = emb
                break
        likes_nodes = []
        comments_nodes = []
        if sc:
            try:
                likes_nodes = fetch_post_likes(session, sc, MAX_LIKES_PER_POST)
            except Exception:
                likes_nodes = []
            try:
                comments_nodes = fetch_post_comments(session, sc, MAX_COMMENTS_PER_POST)
            except Exception:
                comments_nodes = []
        n["_likes_nodes"] = likes_nodes
        n["_comments_nodes"] = comments_nodes
        tagged.append(n)
        rnd_sleep()

    # 5) build HTML
    print(f"[i] Counts → Followers: {len(followers)} | Following: {len(following)} | Posts: {len(posts)} | Reels: {len(reels)} | Tagged: {len(tagged_nodes)}")
    print("[i] Building HTML report ...")
    try:
        build_html_report(out_html, username, user_id, profile, followers, following, posts, reels, tagged)
    except Exception as e:
        print("[ERROR] Failed building HTML:", e)
        sys.exit(1)

    print("[i] Done.")

if __name__ == "__main__":
    main()
