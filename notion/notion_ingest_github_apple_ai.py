#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "apple-fm-sdk",
#     "click",
#     "loguru",
#     "requests",
# ]
# ///
"""
notion_ingest_github_apple_ai.py

Mac-only (Apple Intelligence) Notion ingester:
- Input: GitHub repo URL (public)
- Fetch README via GitHub API
- Use Apple Foundation Models SDK for Python (apple_fm_sdk) to:
    - generate Notes (short description)
    - choose up to 10 Tags ONLY from existing Notion multi_select options
    - output confidence + suggested tags
- Write create-only page to Notion DB properties:
    Notes (Text/rich_text), Tags (multi_select), URL (url)

Install:
  pip install click loguru requests apple-fm-sdk

Env vars:
  NOTION_TOKEN=secret_...
  NOTION_DATABASE_ID=...

Run:
  python notion_ingest_github_apple_ai.py https://github.com/apple/python-apple-fm-sdk --dry-run -v
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import click
import requests
from click.core import ParameterSource
from loguru import logger

import apple_fm_sdk as fm


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def mask_secret(value: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
    value = value or ""
    if not value:
        return "<empty>"
    if len(value) <= prefix_len + suffix_len:
        return f"{value[:1]}... (len={len(value)})"
    return f"{value[:prefix_len]}...{value[-suffix_len:]} (len={len(value)})"


def get_value_hints(value: Optional[str]) -> List[str]:
    hints: List[str] = []
    if value is None:
        return hints
    if value != value.strip():
        hints.append("contains leading or trailing whitespace")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        hints.append("appears to include surrounding quotes")
    return hints


def get_param_source_label(ctx: Optional[click.Context], param_name: str) -> str:
    if ctx is None:
        return "unknown"
    source = ctx.get_parameter_source(param_name)
    if source == ParameterSource.COMMANDLINE:
        return "cli"
    if source == ParameterSource.ENVIRONMENT:
        return "env"
    if source == ParameterSource.DEFAULT:
        return "default"
    return "unknown"


def log_auth_debug(
    notion_token: Optional[str],
    database_id: Optional[str],
    notion_token_source: str,
    database_id_source: str,
) -> None:
    logger.info("Notion token source: {}", notion_token_source)
    logger.info("Notion token preview: {}", mask_secret(notion_token or ""))
    for hint in get_value_hints(notion_token):
        logger.warning("Notion token hint: {}", hint)

    logger.info("Notion database id source: {}", database_id_source)
    logger.info("Notion database id preview: {}", mask_secret(database_id or "", prefix_len=6, suffix_len=6))
    for hint in get_value_hints(database_id):
        logger.warning("Notion database id hint: {}", hint)


def build_preview_payload(notes: str, tags: List[str], repo_url: str, model_out: dict) -> dict:
    return {"Notes": notes, "Tags": tags, "URL": repo_url, "model_raw": model_out}


# ----------------------------
# GitHub parsing + README fetch
# ----------------------------

@dataclass(frozen=True)
class GitHubRepo:
    owner: str
    repo: str
    url: str


def parse_github_repo_url(url: str) -> GitHubRepo:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"URL must start with http(s): {url}")

    parsed = urlparse(url)
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only github.com URLs are supported for now.")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include /owner/repo")

    owner, repo = parts[0], parts[1]
    repo = repo[:-4] if repo.endswith(".git") else repo
    normalized = f"https://github.com/{owner}/{repo}"
    return GitHubRepo(owner=owner, repo=repo, url=normalized)


def fetch_github_readme(repo: GitHubRepo, timeout_s: float = 20.0) -> str:
    api_url = f"https://api.github.com/repos/{repo.owner}/{repo.repo}/readme"
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "User-Agent": "notion-ingest-github-apple-ai",
    }
    r = requests.get(api_url, headers=headers, timeout=timeout_s)
    if r.status_code == 404:
        raise RuntimeError("README not found via GitHub API (404).")
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API error {r.status_code}: {r.text[:300]}")
    logger.debug("Fetched README for %s/%s: %d bytes", repo.owner, repo.repo, len(r.text or ""))
    return r.text or ""


# ----------------------------
# Notion API client
# ----------------------------

class NotionClient:
    def __init__(self, token: str, timeout_s: float = 20.0):
        self.timeout_s = timeout_s
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
                "User-Agent": "notion-ingest-github-apple-ai",
            }
        )

    def get_database(self, database_id: str) -> dict:
        url = f"{NOTION_API_BASE}/databases/{database_id}"
        r = self.session.get(url, timeout=self.timeout_s)
        if r.status_code >= 400:
            raise RuntimeError(f"Notion get_database error {r.status_code}: {r.text[:500]}")
        return r.json()

    def create_page(self, database_id: str, notes: str, tags: List[str], url_value: str) -> dict:
        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                # Notion "Text" property uses rich_text in API
                "Notes": {"rich_text": [{"type": "text", "text": {"content": notes}}]},
                "Tags": {"multi_select": [{"name": t} for t in tags]},
                "URL": {"url": url_value},
            },
        }
        url = f"{NOTION_API_BASE}/pages"
        r = self.session.post(url, data=json.dumps(payload), timeout=self.timeout_s)
        if r.status_code >= 400:
            raise RuntimeError(f"Notion create_page error {r.status_code}: {r.text[:700]}")
        return r.json()


def get_allowed_tag_options(db_obj: dict, tags_property_name: str = "Tags") -> List[str]:
    props = db_obj.get("properties", {})
    if tags_property_name not in props:
        raise KeyError(f"Database does not have a '{tags_property_name}' property.")
    tags_prop = props[tags_property_name]
    if tags_prop.get("type") != "multi_select":
        raise TypeError(f"'{tags_property_name}' is not a multi_select property.")
    options = tags_prop.get("multi_select", {}).get("options", [])
    return [o.get("name", "").strip() for o in options if o.get("name")]


# ----------------------------
# Apple Intelligence (Foundation Models) generation
# ----------------------------

def _compact_readme(readme: str, max_chars: int = 12000) -> str:
    """
    Lightly trim README to reduce context size.
    Keep the beginning; that usually contains the description/overview.
    """
    readme = readme.strip()
    if len(readme) <= max_chars:
        return readme
    return readme[: max_chars - 1].rstrip() + "…"


def build_output_schema(allowed_tags: List[str]) -> dict:
    """
    Guided-generation JSON schema for structured output.
    'selected_tags' is constrained to existing Notion tag options (enum).
    """
    # If allowed_tags is empty, schema must allow empty selected_tags without enum
    tag_item_schema = {"type": "string"} if not allowed_tags else {"type": "string", "enum": allowed_tags}

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["notes", "selected_tags", "confidence", "suggested_tags"],
        "properties": {
            "notes": {
                "type": "string",
                "description": "1–3 sentence description of the tool/pipeline based on README.",
                "minLength": 20,
                "maxLength": 900,
            },
            "selected_tags": {
                "type": "array",
                "description": "Choose up to 10 tags strictly from allowed options.",
                "items": tag_item_schema,
                "minItems": 0,
                "maxItems": 10,
                "uniqueItems": True,
            },
            "confidence": {
                "type": "number",
                "description": "0.0–1.0 confidence in selected_tags being correct.",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "suggested_tags": {
                "type": "array",
                "description": "Free-form suggestions for manual tagging (not necessarily in allowed options).",
                "items": {"type": "string"},
                "minItems": 0,
                "maxItems": 10,
                "uniqueItems": True,
            },
        },
    }


def _extract_json_object(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise RuntimeError("Apple Intelligence returned empty text.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise RuntimeError("Apple Intelligence did not return valid JSON.")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Apple Intelligence returned malformed JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected Apple Intelligence JSON object, got {type(parsed)}")
    return parsed


def _coerce_model_response(response: Any) -> dict:
    if isinstance(response, dict):
        return response

    for attr in ("text", "content"):
        value = getattr(response, attr, None)
        if isinstance(value, str):
            return _extract_json_object(value)

    if isinstance(response, str):
        return _extract_json_object(response)

    raise RuntimeError(f"Unexpected model output type: {type(response)}")


def _build_json_repair_prompt(base_prompt: str, invalid_response: Any, parse_error: Exception) -> str:
    invalid_text = str(invalid_response or "").strip()
    invalid_text = invalid_text[:1500]
    return (
        f"{base_prompt}\n\n"
        "You did not return valid JSON in the previous reply.\n"
        f"Parser error: {parse_error}\n"
        "Previous reply:\n"
        f"{invalid_text}\n\n"
        "Return only a valid JSON object with the required keys. No prose, no markdown, no code fences."
    )


def _validate_model_output(model_out: dict) -> dict:
    required = {"notes", "selected_tags", "confidence", "suggested_tags"}
    missing = sorted(required - set(model_out))
    if missing:
        raise RuntimeError(f"Apple Intelligence JSON missing required keys: {', '.join(missing)}")

    notes = str(model_out.get("notes") or "").strip()
    selected_tags = model_out.get("selected_tags")
    suggested_tags = model_out.get("suggested_tags")

    try:
        confidence = float(model_out.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Apple Intelligence JSON field 'confidence' must be numeric.") from exc

    if not isinstance(selected_tags, list) or not all(isinstance(tag, str) for tag in selected_tags):
        raise RuntimeError("Apple Intelligence JSON field 'selected_tags' must be a list of strings.")
    if not isinstance(suggested_tags, list) or not all(isinstance(tag, str) for tag in suggested_tags):
        raise RuntimeError("Apple Intelligence JSON field 'suggested_tags' must be a list of strings.")
    if not notes:
        raise RuntimeError("Apple Intelligence JSON field 'notes' must be non-empty.")

    return {
        "notes": notes,
        "selected_tags": selected_tags,
        "confidence": confidence,
        "suggested_tags": suggested_tags,
    }


async def ai_generate_notes_and_tags(
    repo_url: str,
    readme: str,
    allowed_tags: List[str],
    timeout_s: float = 60.0,
) -> dict:
    """
    Uses the on-device Apple system model to return a dict matching build_output_schema().
    """
    model = fm.SystemLanguageModel(
        use_case=fm.SystemLanguageModelUseCase.CONTENT_TAGGING
    )
    is_available, reason = model.is_available()
    if not is_available:
        raise RuntimeError(f"Apple Intelligence model unavailable: {reason}")

    session = fm.LanguageModelSession(
        model=model,
        instructions=(
            "You are a precise cataloging assistant.\n"
            "Return ONLY the JSON object that matches the provided schema.\n"
            "Do not invent tags outside the allowed list for selected_tags.\n"
            "If unsure, keep selected_tags empty and lower confidence, but still provide suggested_tags.\n"
            "Keep notes factual, short, and based on README."
        ),
    )

    schema = build_output_schema(allowed_tags)
    readme_trim = _compact_readme(readme)

    prompt = (
        f"GitHub URL:\n{repo_url}\n\n"
        "README:\n"
        f"{readme_trim}\n\n"
        "Allowed Notion tags (selected_tags MUST be from this list):\n"
        f"{', '.join(allowed_tags) if allowed_tags else '(no tags configured)'}\n\n"
        "Task:\n"
        "- Write 'notes' as a 1–3 sentence description of the tool or pipeline.\n"
        "- Choose up to 10 best-fit 'selected_tags' from the allowed list.\n"
        "- Provide 'confidence' from 0.0 to 1.0.\n"
        "- Provide 'suggested_tags' (up to 10) to help a human tag if uncertain.\n"
    )

    try:
        result = await asyncio.wait_for(session.respond(prompt, json_schema=schema), timeout=timeout_s)
        return _validate_model_output(_coerce_model_response(result))
    except Exception as schema_exc:
        logger.warning("Guided JSON generation failed; retrying without schema. Details: {}", schema_exc)

    fallback_prompt = (
        f"{prompt}\n"
        "Return only valid JSON with exactly these keys:\n"
        '{'
        '"notes": "string", '
        '"selected_tags": ["string"], '
        '"confidence": 0.0, '
        '"suggested_tags": ["string"]'
        "}\n"
        "Do not wrap the JSON in markdown fences or any explanation."
    )
    fallback_result = await asyncio.wait_for(session.respond(fallback_prompt), timeout=timeout_s)
    fallback_error: Optional[RuntimeError] = None
    try:
        return _validate_model_output(_coerce_model_response(fallback_result))
    except RuntimeError as fallback_exc:
        fallback_error = fallback_exc
        logger.warning("Unguided JSON generation returned invalid output; retrying once. Details: {}", fallback_exc)

    repair_prompt = _build_json_repair_prompt(fallback_prompt, fallback_result, fallback_error)
    repair_result = await asyncio.wait_for(session.respond(repair_prompt), timeout=timeout_s)
    try:
        return _validate_model_output(_coerce_model_response(repair_result))
    except RuntimeError as repair_exc:
        raise RuntimeError(
            "Apple Intelligence returned invalid JSON after fallback retry. "
            f"Last error: {repair_exc}"
        ) from repair_exc


def finalize_tags_and_notes(
    model_out: dict,
    allowed_tags: List[str],
    uncategorized_name: str = "Uncategorized",
    confidence_threshold: float = 0.60,
) -> Tuple[str, List[str]]:
    notes = (model_out.get("notes") or "").strip()
    selected = model_out.get("selected_tags") or []
    confidence = float(model_out.get("confidence") or 0.0)
    suggested = model_out.get("suggested_tags") or []

    # Enforce constraints defensively
    selected = [t for t in selected if t in allowed_tags][:10]
    suggested = [str(s).strip() for s in suggested if str(s).strip()][:10]

    if confidence < confidence_threshold or not selected:
        if uncategorized_name in allowed_tags:
            tags_to_write = [uncategorized_name]
        else:
            tags_to_write = []

        if suggested:
            notes = notes.rstrip() + "\n\nSuggested tags (manual review): " + ", ".join(suggested)
        return notes, tags_to_write

    return notes, selected[:10]


# ----------------------------
# CLI
# ----------------------------

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("github_url", type=str)
@click.option("--notion-token", envvar="NOTION_TOKEN", default=None, help="Notion integration token (or set NOTION_TOKEN).")
@click.option("--database-id", envvar="NOTION_DATABASE_ID", default=None, help="Target Notion database ID (or set NOTION_DATABASE_ID).")
@click.option("--timeout", "timeout_s", type=float, default=20.0, show_default=True, help="HTTP timeout (seconds).")
@click.option("-a","--ai-timeout", "ai_timeout_s", type=float, default=60.0, show_default=True, help="Apple model timeout (seconds).")
@click.option("-n", "--dry-run", is_flag=True, help="Do not write to Notion; print what would be written.")
@click.option("-d","--debug-auth", is_flag=True, help="Print masked Notion credential diagnostics.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging.")
def main(
    github_url: str,
    notion_token: Optional[str],
    database_id: Optional[str],
    timeout_s: float,
    ai_timeout_s: float,
    dry_run: bool,
    debug_auth: bool,
    verbose: bool,
):
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", backtrace=False, diagnose=False)
    ctx = click.get_current_context(silent=True)
    notion_token_source = get_param_source_label(ctx, "notion_token")
    database_id_source = get_param_source_label(ctx, "database_id")

    if not notion_token:
        raise click.ClickException("Missing Notion token. Provide --notion-token or set NOTION_TOKEN.")
    if not database_id:
        raise click.ClickException("Missing database id. Provide --database-id or set NOTION_DATABASE_ID.")
    if debug_auth:
        log_auth_debug(
            notion_token=notion_token,
            database_id=database_id,
            notion_token_source=notion_token_source,
            database_id_source=database_id_source,
        )

    try:
        repo = parse_github_repo_url(github_url)
    except Exception as e:
        raise click.ClickException(str(e))

    logger.info("Repo: {}/{} ({})", repo.owner, repo.repo, repo.url)

    # Fetch README
    try:
        readme = fetch_github_readme(repo, timeout_s=timeout_s)
    except Exception as e:
        raise click.ClickException(f"Failed to fetch README: {e}")

    if not readme.strip():
        logger.warning("README fetched but appears empty.")

    # Read Notion DB to get allowed Tags
    notion = NotionClient(token=notion_token, timeout_s=timeout_s)
    try:
        db_obj = notion.get_database(database_id)
        allowed_tags = get_allowed_tag_options(db_obj, tags_property_name="Tags")
    except Exception as e:
        raise click.ClickException(f"Failed to read Notion database schema/options: {e}")

    if not allowed_tags:
        logger.warning("No existing tag options found in Notion 'Tags' property.")

    # Apple Intelligence: generate Notes + Tags
    try:
        model_out = asyncio.run(
            ai_generate_notes_and_tags(
                repo_url=repo.url,
                readme=readme,
                allowed_tags=allowed_tags,
                timeout_s=ai_timeout_s,
            )
        )
    except Exception as e:
        raise click.ClickException(
            "Apple Intelligence generation failed. "
            "Check that Apple Intelligence is enabled and the model is available. "
            f"Details: {e}"
        )

    notes, tags_to_write = finalize_tags_and_notes(
        model_out=model_out,
        allowed_tags=allowed_tags,
        uncategorized_name="Uncategorized",
        confidence_threshold=0.60,
    )

    preview = build_preview_payload(notes=notes, tags=tags_to_write, repo_url=repo.url, model_out=model_out)

    if dry_run:
        click.echo(json.dumps(preview, indent=2, ensure_ascii=False))
        try:
            notion.get_database(database_id)
        except Exception as e:
            raise click.ClickException(f"Dry-run Notion validation failed: {e}")
        logger.info("Dry-run Notion validation succeeded.")
        logger.info("Dry-run complete (no Notion write).")
        return

    # Create-only page
    try:
        created = notion.create_page(database_id=database_id, notes=notes, tags=tags_to_write, url_value=repo.url)
    except Exception as e:
        raise click.ClickException(f"Failed to create Notion page: {e}")

    page_id = created.get("id", "<unknown>")
    logger.info("Created Notion page id: {}", page_id)
    click.echo(json.dumps({"status": "created", "page_id": page_id, "url": repo.url, "tags": tags_to_write}, indent=2))


if __name__ == "__main__":
    main()
