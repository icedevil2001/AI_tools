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
"""
Fetch Medium articles via Playwright, convert to Markdown, and save to disk.
Keeps a simple JSON state of previously processed URLs to avoid duplicates.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
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
        print("Please complete login in the browser window, then press Enter to continue...")
        try:
            input()
        except EOFError:
            pass
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass
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
) -> None:
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
    storage_state_exists = storage_state_path.exists()
    storage_state_arg = str(storage_state_path) if storage_state_exists else None

    if reuse_session_only and not storage_state_exists:
        raise SystemExit(f"Storage state not found at {storage_state}. Run once with --save-storage-state.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        context = await browser.new_context(storage_state=storage_state_arg)
        page = await context.new_page()

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
        )
    )


if __name__ == "__main__":
    main()
