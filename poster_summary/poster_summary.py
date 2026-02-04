#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click","openai","python-dotenv","markdown","pillow","pillow-heif","loguru"]
# ///
"""Poster summarization CLI.

Clean implementation; previous corrupted fragments removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import base64
import re
import os
import sys
import click
from dotenv import load_dotenv
from PIL import Image
import pillow_heif  # type: ignore
from loguru import logger
import io

pillow_heif.register_heif_opener()
load_dotenv()

try:
    import markdown  # type: ignore
except ImportError:  # pragma: no cover
    markdown = None  # type: ignore
    logger.warning("Package 'markdown' not installed; HTML will show raw markdown inside <pre>.")

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS  # Pillow >=9.1
except AttributeError:  # pragma: no cover
    # Minimal fallback: omit explicit resample if not available.
    RESAMPLE_LANCZOS = None

SYSTEM_PROMPT = """
You are an expert at analyzing scientific or academic posters. Produce MARKDOWN with exactly these top-level sections:

# <Title>
## Analysis
### Sections
### Impact
### Limitations
### Main Takeaway
### Keywords
## Poster Contents

Instructions:
- First line: extracted poster title as H1.
- Under Analysis, synthesize insights (no verbatim copying) organized by the listed subheadings; omit a subheading if empty.
- Under Poster Contents, provide raw transcription (verbatim text, headings, figure/table captions) with minimal formatting; preserve line breaks where practical.
- If some text is unreadable use [UNREADABLE].
- Do NOT add additional top-level headings; only the ones specified.
- Avoid extraneous commentary. Output only the markdown.
End with the Poster Contents section.
"""

@dataclass
class Poster:
    image_path: Path
    summary: str = ""

    @property
    def encode_image(self) -> str:
        with open(self.image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @property
    def title(self) -> str:
        if not self.summary:
            return self.image_path.stem
        first = self.summary.strip().splitlines()[0]
        return first.lstrip("# ").strip() or self.image_path.stem


def sanitize_title(title: str) -> str:
    cleaned = re.sub(r"[^\w\s]+", "", title)
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:150] or "poster"


def resize_image(orig_path: str | Path, max_edge: int, resized_path: Path) -> Path:
    orig_path = Path(orig_path)
    with Image.open(orig_path) as img:
        w, h = img.size
        scale = max_edge / max(w, h)
        if scale < 1:
            new_size = (int(w * scale), int(h * scale))
            if RESAMPLE_LANCZOS is not None:
                img = img.resize(new_size, RESAMPLE_LANCZOS)
            else:
                img = img.resize(new_size)
        img.convert("RGB").save(resized_path, "JPEG", quality=90)
    logger.info(f"Resized image written: {resized_path}")
    return resized_path


def read_prompt_from_file(prompt_path: str) -> str:
    """
    Read the prompt from a markdown file.
    """
    prompt_file = Path(prompt_path)
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file {prompt_file} does not exist.")
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read()
    return prompt



def write_to_html(poster: Poster, full_image_path: Path, html_path: str) -> bool:
    """Write poster HTML with a collapsible 'Poster Contents' section.

    Splits the model output at the first '## Poster Contents' heading (case-insensitive).
    Everything before is treated as analysis/summary; the heading and remainder become
    the raw transcription section.
    """
    try:
        raw_md = poster.summary or ""
        match = re.search(r"^##\s*Poster Contents.*$", raw_md, flags=re.MULTILINE | re.IGNORECASE)
        if match:
            analysis_md = raw_md[:match.start()].strip()
            contents_md = raw_md[match.start():].strip()
        else:
            analysis_md = raw_md.strip()
            contents_md = "## Poster Contents\n(No raw transcription section was produced.)"

        lines = analysis_md.splitlines()
        if lines and lines[0].startswith('# '):
            title = lines[0][2:].strip()
            analysis_body_md = '\n'.join(lines[1:]).strip()
        else:
            title = poster.title
            analysis_body_md = analysis_md

        if markdown:
            analysis_html = markdown.markdown(analysis_body_md)
            contents_html = markdown.markdown(contents_md)
        else:
            from html import escape
            analysis_html = f"<pre>{escape(analysis_body_md)}</pre>"
            contents_html = f"<pre>{escape(contents_md)}</pre>"

        thumb_b64 = poster.encode_image
        # Always convert original to JPEG for browser compatibility (HEIC not widely supported)
        try:
            with Image.open(full_image_path) as im_full:
                buf = io.BytesIO()
                im_full.convert('RGB').save(buf, format='JPEG', quality=95)
                full_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        except Exception as ex:  # fallback direct bytes (may fail to display if HEIC)
            logger.warning(f"Failed to transcode full image to JPEG ({ex}); embedding raw bytes.")
            with open(full_image_path, 'rb') as fh:
                full_b64 = base64.b64encode(fh.read()).decode('utf-8')

        html_doc = f"""<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1.0'>
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
        h1 {{ margin-top: 0; }}
        img.poster-thumb {{ max-width: 100%; height: auto; cursor: pointer; border: 1px solid #ddd; box-shadow: 0 2px 4px rgba(0,0,0,.1); }}
        details {{ margin: 1.5rem 0; }}
        details > summary {{ cursor: pointer; font-weight: 600; background: #f5f5f5; padding: .6rem .8rem; border: 1px solid #ddd; border-radius: 4px; }}
        .contents-wrapper {{ padding: 1rem; border: 1px solid #e0e0e0; border-top: 0; background: #fff; }}
        #modal {{ display: none; position: fixed; z-index: 1000; inset: 0; background: rgba(0,0,0,.85); justify-content: center; align-items: center; }}
        #modal img {{ max-width: 95%; max-height: 95%; }}
        .meta-note {{ font-size: .78rem; color: #666; text-align: center; margin-top: .4rem; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class='thumb-container'>
        <img id='poster-img' class='poster-thumb' src='data:image/jpeg;base64,{thumb_b64}' alt='Poster Thumbnail'>
        <div class='meta-note'>Click image to view full resolution</div>
    </div>
    <section id='analysis'>
        {analysis_html}
    </section>
    <details id='raw-contents'>
        <summary>Poster Contents (raw transcription)</summary>
        <div class='contents-wrapper'>
            {contents_html}
        </div>
    </details>
    <div id='modal' onclick="this.style.display='none'">
        <img src='data:image/jpeg;base64,{full_b64}' alt='Full Resolution Poster'>
    </div>
    <script>
        document.getElementById('poster-img').addEventListener('click', () => {{
            document.getElementById('modal').style.display = 'flex';
        }});
    </script>
</body>
</html>"""
        out_path = Path(html_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_doc, encoding='utf-8')
        logger.info(f"Wrote HTML output to {out_path}")
        return True
    except (OSError, ValueError) as e:
        logger.error(f"Failed writing HTML {html_path}: {e}")
        return False


def format_output_with_agent(client, content: str, model: str = "gpt-5-nano") -> str:
    """Optional second pass to clean markdown formatting."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Format text into clean markdown; preserve headings, lists."},
            {"role": "user", "content": content},
        ],
    )
    return resp.choices[0].message.content


def ensure_openai_client():
    from openai import OpenAI  # local import to avoid unused warning if not executed
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set; create .env or export variable.")
    return OpenAI(api_key=api_key)


def generate_poster_summary(client, poster: Poster, model: str, user_prompt: str, additional_formatting: bool) -> None:
    """Call vision model to produce structured poster summary."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{poster.encode_image}"}},
            ]},
        ],
    )
    summary = resp.choices[0].message.content
    if additional_formatting:
        summary = format_output_with_agent(client, summary)
    poster.summary = summary


def write_to_markdown(poster: Poster, md_path: Path) -> None:
    md_path.write_text(f"![Poster Image]({poster.image_path.name})\n\n{poster.summary}", encoding="utf-8")
    logger.info(f"Markdown written: {md_path}")


# (imports consolidated at top)


@click.command(context_settings=dict(help_option_names=["-h", "--help"], show_default=True))
@click.option("--image_path", "-i", required=True, help="Path to poster image (JPEG/PNG/HEIC).")
@click.option("--output_dir", "-o", default=None, help="Output directory (default: CWD).")
@click.option("--prefix", "-p", default=None, help="Filename prefix (default: derived from poster title).")
@click.option("--model", "-m", default="gpt-4o-mini", help="OpenAI model (vision-capable).")
@click.option("--max_edge", "-e", default=1024, help="Max edge length for resize.")
@click.option("--prompt_file", "-f", default="prompt.md", help="User prompt file (optional).")
@click.option("--additional_formatting", "-a", is_flag=True, default=False, help="Apply second formatting pass.")
@click.option("--log_level", "-l", default="INFO", help="Logging level.")
def cli(
    image_path: str | None = None,
    output_dir: str | None = None,
    prefix: str | None = None,
    model: str = "gpt-4o-mini",
    max_edge: int = 1024,
    prompt_file: str = "prompt.md",
    additional_formatting: bool = False,
    log_level: str = "INFO",
):
    """Analyze poster image and generate markdown + HTML outputs."""

    logger.remove()
    logger.add(sys.stderr, level=log_level.upper(), colorize=True,
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{function}</cyan>:<yellow>{line}</yellow> - <level>{message}</level>")

    out_dir = Path(output_dir) if output_dir else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.add(out_dir / "poster_summary.log", level="DEBUG", rotation="1 MB", retention=5)

    if image_path is None:
        raise SystemExit("--image_path is required")
    orig_path = Path(image_path)
    if not orig_path.exists():
        raise FileNotFoundError(f"Image file does not exist: {orig_path}")

    resized_dir = out_dir / "resized"
    resized_dir.mkdir(parents=True, exist_ok=True)
    resized_path = resized_dir / f"{orig_path.stem}_resized.jpg"
    resized_path = resize_image(orig_path, max_edge=max_edge, resized_path=resized_path)

    poster = Poster(resized_path)

    user_prompt = read_prompt_from_file(prompt_file) if Path(prompt_file).exists() else "Please analyze this poster following the system instructions."

    client = ensure_openai_client()
    generate_poster_summary(client, poster, model=model, user_prompt=user_prompt, additional_formatting=additional_formatting)

    if prefix is None:
        prefix = sanitize_title(poster.title)

    md_path = out_dir / f"{prefix}.md"
    write_to_markdown(poster, md_path)
    html_path = out_dir / f"{prefix}.html"
    write_to_html(poster, orig_path, str(html_path))

    logger.success("Processing complete")


if __name__ == "__main__":  # pragma: no cover
    # Entry point; Click will parse CLI args from sys.argv
    cli()
