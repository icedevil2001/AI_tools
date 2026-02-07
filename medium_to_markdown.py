#!/usr/bin/env python3
# /// script
# dependencies = [
#   "playwright==1.49.0",
#   "readability-lxml==0.8.1",
#   "markdownify==0.11.6",
#   "click==8.1.7",
#   "lxml_html_clean==0.4.1",
# ]
# ///

from __future__ import annotations

"""
Fetch Medium articles via Playwright, convert to Markdown, and save to disk.
Keeps a simple JSON state of previously processed URLs to avoid duplicates.
"""

# Example usage:
# uv run --script medium_to_markdown.py \
#   --manual-login \
#   --save-storage-state \
#   --urls "https://medium.com/data-science/crime-location-analysis-and-prediction-using-python-and-machine-learning-1d8db9c8b6e6"
#
# uv run --script medium_to_markdown.py \
#   --reuse-session-only \
#   --urls "https://medium.com/data-science/crime-location-analysis-and-prediction-using-python-and-machine-learning-1d8db9c8b6e6"

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, List, Set
from urllib.parse import urlparse

import click
from markdownify import markdownify as md
from playwright.async_api import async_playwright
from readability import Document


def load_urls_from_text(path: Path) -> List[str]:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def load_urls_from_playlist(path: Path) -> List[str]:
    """
    Playlist format (JSON):
    - {"urls": ["https://medium.com/..."]}
    - or {"items": [{"url": "https://medium.com/..."}]}
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    urls: List[str] = []
    if isinstance(data, dict):
        if isinstance(data.get("urls"), list):
            urls.extend([u for u in data["urls"] if isinstance(u, str)])
        if isinstance(data.get("items"), list):
            for item in data["items"]:
                if isinstance(item, dict) and isinstance(item.get("url"), str):
                    urls.append(item["url"])
    elif isinstance(data, list):
        urls.extend([u for u in data if isinstance(u, str)])
    return urls


def normalize_urls(urls: Iterable[str]) -> List[str]:
    cleaned = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        cleaned.append(url)
    # de-dupe while preserving order
    seen = set()
    out = []
    for url in cleaned:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def load_state(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if isinstance(data, dict) and isinstance(data.get("seen"), list):
        return set([u for u in data["seen"] if isinstance(u, str)])
    if isinstance(data, list):
        return set([u for u in data if isinstance(u, str)])
    return set()


def save_state(path: Path, seen: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen": sorted(seen)}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "medium-article"


def filename_for(url: str, title: str | None) -> str:
    if title:
        base = slugify(title)[:120]
    else:
        base = slugify(urlparse(url).path.split("/")[-1])[:120]
    if not base:
        base = "medium-article"
    url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{url_hash}.md"


async def fetch_markdown(page, url: str, timeout_ms: int) -> tuple[str | None, str]:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    # Medium sometimes shows an anti-bot interstitial; wait it out if it appears.
    for _ in range(2):
        try:
            title = await page.title()
        except Exception:
            title = ""
        if title and "just a moment" in title.lower():
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except Exception:
                pass
            try:
                await page.wait_for_selector("article", timeout=timeout_ms)
            except Exception:
                pass
            continue
        break
    try:
        await page.wait_for_selector("article", timeout=timeout_ms)
    except Exception:
        # Some Medium pages render without <article> but still have content.
        pass
    html = await page.content()
    title = None
    try:
        title = await page.title()
    except Exception:
        title = None

    doc = Document(html)
    summary_html = doc.summary(html_partial=True)
    extracted_title = doc.title() or title
    markdown = md(summary_html, heading_style="ATX")

    lowered = (extracted_title or "").lower()
    blocked = any(
        token in lowered
        for token in (
            "just a moment",
            "checking your browser",
            "verify you are human",
        )
    )
    if blocked or "verify you are human" in markdown.lower():
        json_title, json_md = fetch_medium_json(url, timeout_ms)
        if json_md:
            return json_title or extracted_title, json_md
        jina_title, jina_md = fetch_jina_fallback(url, timeout_ms)
        if jina_md:
            return jina_title or extracted_title, jina_md

    return extracted_title, markdown


def build_frontmatter(url: str, title: str | None) -> str:
    safe_title = title.replace("\n", " ").strip() if title else ""
    return "\n".join(
        [
            "---",
            f'title: "{safe_title}"' if safe_title else 'title: ""',
            f'source: "{url}"',
            "---",
            "",
        ]
    )


def maybe_install_browsers(install_browsers: bool) -> None:
    if not install_browsers:
        return
    subprocess.check_call([sys.executable, "-m", "playwright", "install"])


def load_credentials(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def save_credentials(path: Path, email: str, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"email": email, "password": password}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_netscape_cookies(path: Path, domain_filter: str | None) -> List[dict]:
    cookies: List[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
            http_only = True
        else:
            http_only = False
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path_val, secure_val, expires, name, value = parts[:7]
        if domain_filter and not domain.endswith(domain_filter):
            continue
        try:
            expires_ts = int(expires)
        except ValueError:
            expires_ts = -1
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path_val or "/",
                "expires": expires_ts if expires_ts > 0 else -1,
                "httpOnly": http_only,
                "secure": secure_val.lower() == "true",
                "sameSite": "Lax",
            }
        )
    return cookies


def parse_json_cookies(path: Path, domain_filter: str | None) -> List[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    cookies: List[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        domain = item.get("domain")
        if not isinstance(domain, str):
            continue
        if domain_filter and not domain.endswith(domain_filter):
            continue
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        path_val = item.get("path") if isinstance(item.get("path"), str) else "/"
        http_only = bool(item.get("httpOnly"))
        secure = bool(item.get("secure"))
        same_site_raw = item.get("sameSite")
        if isinstance(same_site_raw, str):
            same_site_raw = same_site_raw.lower()
        if same_site_raw in {"no_restriction", "none"}:
            same_site = "None"
        elif same_site_raw in {"strict"}:
            same_site = "Strict"
        else:
            same_site = "Lax"
        expires_val = item.get("expirationDate")
        if isinstance(expires_val, (int, float)):
            expires = int(expires_val)
        else:
            expires = -1
        if item.get("session") is True:
            expires = -1
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path_val,
                "expires": expires,
                "httpOnly": http_only,
                "secure": secure,
                "sameSite": same_site,
            }
        )
    return cookies


def import_cookies_to_storage_state(
    cookies_path: Path,
    storage_state_path: Path,
    domain_filter: str | None,
    store_copy_path: Path | None,
) -> None:
    try:
        raw = cookies_path.read_text(encoding="utf-8", errors="replace").lstrip()
    except FileNotFoundError:
        raise SystemExit(f"Cookie file not found: {cookies_path}")
    if raw.startswith("[") or raw.startswith("{") or cookies_path.suffix.lower() == ".json":
        cookies = parse_json_cookies(cookies_path, domain_filter=domain_filter)
    else:
        cookies = parse_netscape_cookies(cookies_path, domain_filter=domain_filter)
    if not cookies:
        raise SystemExit(
            f"No cookies matched domain filter {domain_filter!r} in {cookies_path}."
        )
    names = sorted({c.get("name", "") for c in cookies if c.get("name")})
    if names:
        print(f"Imported cookies: {', '.join(names)}")
    if "cf_clearance" not in names:
        print("Warning: cf_clearance not present; Cloudflare may block access.")
    if store_copy_path:
        store_copy_path.parent.mkdir(parents=True, exist_ok=True)
        store_copy_path.write_text(
            cookies_path.read_text(encoding="utf-8", errors="replace"),
            encoding="utf-8",
        )
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cookies": cookies, "origins": []}
    storage_state_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def fetch_text_url(url: str, timeout_ms: int) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def fetch_medium_json(url: str, timeout_ms: int) -> tuple[str | None, str | None]:
    joiner = "&" if "?" in url else "?"
    json_url = f"{url}{joiner}format=json"
    try:
        text = fetch_text_url(json_url, timeout_ms)
    except (urllib.error.URLError, urllib.error.HTTPError):
        return None, None
    if "while(1);" in text:
        text = text.split("while(1);", 1)[-1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, None

    payload = data.get("payload") if isinstance(data, dict) else None
    if not isinstance(payload, dict):
        return None, None
    value = payload.get("value")
    if not isinstance(value, dict):
        return None, None

    title = value.get("title") if isinstance(value.get("title"), str) else None

    content = value.get("content")
    if not isinstance(content, dict):
        return title, None
    body_model = content.get("bodyModel")
    if not isinstance(body_model, dict):
        return title, None
    paragraphs = body_model.get("paragraphs")
    if not isinstance(paragraphs, list):
        return title, None

    lines: List[str] = []
    for para in paragraphs:
        if not isinstance(para, dict):
            continue
        text = para.get("text")
        if not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        if para.get("type") == 3:
            lines.append(f"## {text}")
        else:
            lines.append(text)

    if not lines:
        return title, None
    return title, "\n\n".join(lines).strip() + "\n"


def fetch_jina_fallback(url: str, timeout_ms: int) -> tuple[str | None, str | None]:
    jina_url = f"https://r.jina.ai/http://{url}"
    try:
        text = fetch_text_url(jina_url, timeout_ms)
    except (urllib.error.URLError, urllib.error.HTTPError):
        return None, None
    text = text.strip()
    if not text:
        return None, None
    title = None
    first_line = text.splitlines()[0].strip()
    if first_line.startswith("# "):
        title = first_line[2:].strip()
    return title, text + "\n"


async def maybe_login(
    page,
    login: bool,
    timeout_ms: int,
    email: str | None,
    password: str | None,
    login_url: str,
    manual_login: bool,
) -> None:
    if not login:
        return

    await page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)

    if manual_login:
        print(
            "Complete login or any human-verification in the browser window. "
            "Press Enter to continue, or just wait for the page to proceed automatically..."
        )

        start = time.monotonic()
        input_task = None
        if sys.stdin and sys.stdin.isatty():
            loop = asyncio.get_running_loop()
            input_task = loop.run_in_executor(None, sys.stdin.readline)

        try:
            while True:
                if input_task and input_task.done():
                    break

                try:
                    title = await page.title()
                except Exception:
                    title = ""

                title_lc = title.lower()
                is_interstitial = any(
                    token in title_lc
                    for token in (
                        "just a moment",
                        "checking your browser",
                        "verify you are human",
                    )
                )

                # Auto-continue once we are past the interstitial or the URL changed.
                if not is_interstitial and page.url != login_url:
                    break
                try:
                    if not is_interstitial and await page.locator("article").count() > 0:
                        break
                except Exception:
                    pass

                if (time.monotonic() - start) * 1000 > timeout_ms:
                    break

                await page.wait_for_timeout(1000)
        finally:
            if input_task and not input_task.done():
                input_task.cancel()
        return
    try:
        await page.get_by_role("button", name=re.compile(r"sign in with email", re.I)).click()
    except Exception:
        # Fallback to email input if button isn't present
        pass

    if email:
        try:
            await page.get_by_label(re.compile(r"email", re.I)).fill(email)
        except Exception:
            try:
                await page.locator('input[type="email"]').fill(email)
            except Exception:
                pass
        try:
            await page.get_by_role("button", name=re.compile(r"continue|next|sign in", re.I)).click()
        except Exception:
            pass

    if password:
        try:
            await page.get_by_label(re.compile(r"password", re.I)).fill(password)
        except Exception:
            try:
                await page.locator('input[type="password"]').fill(password)
            except Exception:
                pass
        try:
            await page.get_by_role("button", name=re.compile(r"sign in|submit|continue", re.I)).click()
        except Exception:
            pass

    # Give the session a moment to settle if a redirect occurs.
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass


async def run(
    urls_arg: str | None,
    input_path: str | None,
    playlist_path: str | None,
    outdir: str,
    state_path: str,
    delay: float,
    timeout_ms: int,
    install_browsers: bool,
    login: bool,
    email: str | None,
    password: str | None,
    login_url: str,
    manual_login: bool,
    credentials_file: str,
    save_credentials_flag: bool,
    storage_state: str,
    save_storage_state: bool,
    headed: bool,
    reuse_session_only: bool,
    user_data_dir: str | None,
    channel: str | None,
    import_cookies: str | None,
    import_domain: str | None,
    import_cookies_store: str | None,
    debug_network: bool,
) -> None:
    if manual_login and not login:
        login = True
    if manual_login and not headed:
        headed = True

    maybe_install_browsers(install_browsers)

    urls: List[str] = []
    if urls_arg:
        urls.extend([u for u in urls_arg.split(",") if u.strip()])
    if input_path:
        urls.extend(load_urls_from_text(Path(input_path)))
    if playlist_path:
        urls.extend(load_urls_from_playlist(Path(playlist_path)))

    urls = normalize_urls(urls)
    if not urls:
        raise SystemExit("No URLs provided. Use --urls, --input, or --playlist.")

    state_path_obj = Path(state_path)
    seen = load_state(state_path_obj)

    outdir_obj = Path(outdir)
    outdir_obj.mkdir(parents=True, exist_ok=True)

    creds_path = Path(credentials_file)
    if not email or not password:
        cached = load_credentials(creds_path)
        email = email or cached.get("email")
        password = password or cached.get("password")

    if save_credentials_flag and email and password:
        save_credentials(creds_path, email, password)

    processed = 0
    skipped = 0

    storage_state_path = Path(storage_state)
    if import_cookies:
        domain_filter = import_domain
        if domain_filter and domain_filter.strip().lower() in {"", "none", "*", "all"}:
            domain_filter = None
        store_path = Path(import_cookies_store) if import_cookies_store else None
        import_cookies_to_storage_state(
            Path(import_cookies),
            storage_state_path,
            domain_filter=domain_filter,
            store_copy_path=store_path,
        )
        reuse_session_only = True
        login = False
    elif import_cookies_store:
        stored_path = Path(import_cookies_store)
        if stored_path.exists():
            domain_filter = import_domain
            if domain_filter and domain_filter.strip().lower() in {"", "none", "*", "all"}:
                domain_filter = None
            import_cookies_to_storage_state(
                stored_path,
                storage_state_path,
                domain_filter=domain_filter,
                store_copy_path=None,
            )
            reuse_session_only = True
            login = False
    storage_state_exists = storage_state_path.exists()
    storage_state_arg = str(storage_state_path) if storage_state_exists else None

    if reuse_session_only and not storage_state_exists:
        raise SystemExit(f"Storage state not found at {storage_state}. Run once with --save-storage-state.")

    async with async_playwright() as p:
        if user_data_dir:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=not headed,
                channel=channel,
            )
            browser = context.browser
        else:
            browser = await p.chromium.launch(headless=not headed, channel=channel)
            context = await browser.new_context(storage_state=storage_state_arg)
        page = await context.new_page()

        if debug_network:
            def log_response(resp):
                try:
                    url = resp.url
                    status = resp.status
                    if "graphql" in url:
                        print(f"[graphql] {status} {url}")
                except Exception:
                    pass
            context.on("response", log_response)

        if not reuse_session_only:
            await maybe_login(
                page,
                login=login,
                timeout_ms=timeout_ms,
                email=email,
                password=password,
                login_url=login_url,
                manual_login=manual_login,
            )

        for url in urls:
            if url in seen:
                skipped += 1
                continue

            title, markdown = await fetch_markdown(page, url, timeout_ms=timeout_ms)
            filename = filename_for(url, title)
            frontmatter = build_frontmatter(url, title)
            outpath = outdir_obj / filename
            outpath.write_text(frontmatter + markdown, encoding="utf-8")

            seen.add(url)
            save_state(state_path_obj, seen)
            processed += 1

            if delay > 0:
                time.sleep(delay)

        if save_storage_state:
            storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(storage_state_path))

        await browser.close()

    print(f"Processed: {processed}, skipped: {skipped}, total: {len(urls)}")


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], show_default=True)

@click.command(context_settings=CONTEXT_SETTINGS)
@click.option("--urls", help="Comma-separated list of URLs.")
@click.option("--input", "input_path", help="Text file with one URL per line.")
@click.option(
    "--playlist",
    "playlist_path",
    help="JSON file containing an array of URLs or {urls:[...]} or {items:[{url:...}]}",
)
@click.option("--outdir", default="output/medium", show_default=True, help="Output directory.")
@click.option("--state", "state_path", default="state/medium_seen.json", show_default=True, help="State file.")
@click.option("--delay", type=float, default=0.0, show_default=True, help="Delay between pages (seconds).")
@click.option("--timeout-ms", type=int, default=45000, show_default=True, help="Navigation timeout.")
@click.option("--install-browsers", is_flag=True, help="Install Playwright browser binaries.")
@click.option("--login", is_flag=True, help="Attempt to log into Medium before fetching.")
@click.option("--email", help="Medium login email (optional).")
@click.option("--password", help="Medium login password (optional).")
@click.option(
    "--login-url",
    default="https://medium.com/m/signin",
    show_default=True,
    help="Login URL (use email magic-link URL if provided).",
)
@click.option(
    "--manual-login",
    is_flag=True,
    help="Pause for you to complete login in the browser, then press Enter.",
)
@click.option(
    "--credentials-file",
    default="state/medium_credentials.json",
    show_default=True,
    help="Plaintext JSON credentials cache (email/password).",
)
@click.option(
    "--save-credentials",
    "save_credentials_flag",
    is_flag=True,
    help="Save email/password into credentials file (plaintext).",
)
@click.option(
    "--storage-state",
    default="state/medium_storage.json",
    show_default=True,
    help="Playwright storage state file (cookies/localStorage).",
)
@click.option(
    "--save-storage-state",
    is_flag=True,
    help="Save storage state after login for reuse.",
)
@click.option("--headed", is_flag=True, help="Run browser with UI (helpful for manual login).")
@click.option(
    "--reuse-session-only",
    is_flag=True,
    help="Require existing storage state and skip any login attempt.",
)
@click.option(
    "--user-data-dir",
    help="Use a persistent browser profile directory (helps pass bot checks).",
)
@click.option(
    "--channel",
    help="Playwright browser channel (e.g. 'chrome', 'msedge').",
)
@click.option(
    "--import-cookies",
    help="Path to Netscape cookies.txt to seed storage state.",
)
@click.option(
    "--import-domain",
    default="medium.com",
    show_default=True,
    help="Only import cookies whose domain ends with this value. Use 'none' to import all.",
)
@click.option(
    "--import-cookies-store",
    default="state/medium_cookies.txt",
    show_default=True,
    help="Cache a copy of the Netscape cookies.txt for reuse.",
)
@click.option(
    "--debug-network",
    is_flag=True,
    help="Log GraphQL response status codes.",
)
def main(
    urls: str | None,
    input_path: str | None,
    playlist_path: str | None,
    outdir: str,
    state_path: str,
    delay: float,
    timeout_ms: int,
    install_browsers: bool,
    login: bool,
    email: str | None,
    password: str | None,
    login_url: str,
    manual_login: bool,
    credentials_file: str,
    save_credentials_flag: bool,
    storage_state: str,
    save_storage_state: bool,
    headed: bool,
    reuse_session_only: bool,
    user_data_dir: str | None,
    channel: str | None,
    import_cookies: str | None,
    import_domain: str | None,
    import_cookies_store: str | None,
    debug_network: bool,
) -> None:
    import asyncio

    asyncio.run(
        run(
            urls_arg=urls,
            input_path=input_path,
            playlist_path=playlist_path,
            outdir=outdir,
            state_path=state_path,
            delay=delay,
            timeout_ms=timeout_ms,
            install_browsers=install_browsers,
            login=login,
            email=email,
            password=password,
            login_url=login_url,
            manual_login=manual_login,
            credentials_file=credentials_file,
            save_credentials_flag=save_credentials_flag,
            storage_state=storage_state,
            save_storage_state=save_storage_state,
            headed=headed,
            reuse_session_only=reuse_session_only,
            user_data_dir=user_data_dir,
            channel=channel,
            import_cookies=import_cookies,
            import_domain=import_domain,
            import_cookies_store=import_cookies_store,
            debug_network=debug_network,
        )
    )


if __name__ == "__main__":
    main()
