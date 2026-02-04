# Poster Summary Tool

A Python CLI script that analyzes poster images using OpenAI's GPT-4 vision model, generates a detailed markdown summary, and produces a standalone HTML page with embedded images.

## Features

- Supports JPEG and HEIC input images (via `pillow-heif`).
- Automatically converts HEIC to JPEG.
- Resizes images so the longest edge is configurable (default: 1024 px).
- Generates a structured markdown summary with:
  - Title extracted from the poster.
  - Detailed summary section.
  - Main takeaway section.
  - Keywords list.
- Creates a Markdown file embedding the resized poster.
- Creates a styled HTML file with:
  - Thumbnail display of the resized poster.
  - Modal/lightbox to view the full-resolution image on click.
  - Responsive CSS and simple JS for interactivity.

## Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/mrmr1993/uv) for running scripts easily in development

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/your-org/poster_summary.git
   cd poster_summary
   ```
2. (Optional) Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies (optional ):
   ```bash
   pip install -r requirements.txt
   ```
   If you do not have a `requirements.txt`, you can install directly:
   ```bash
   pip install click python-dotenv openai markdown pillow pillow-heif
   ```
4. Add your OpenAI API key to a `.env` file in the parent directory:
   ```ini
   OPENAI_API_KEY=sk-...
   ```

## Usage

### Running with UV

The script is configured to work seamlessly with [uv](https://github.com/mrmr1993/uv). Simply run:

```bash
uv run poster_summary.py --image_path -i <path/to/your/image> --output_dir <path/to/output/dir> --prefix <output_prefix>
```

Or using short flags:
```bash
uv run poster_summary.py -i posters/IMG_1245.HEIC
```

#### Options

- `-i, --image_path`  (required)  Path to the input image (JPEG or HEIC).
- `-o, --output_dir`  (optional)  Directory where outputs will be saved. Defaults to current working directory.
- `-p, --prefix`      (optional)  Prefix for output filenames. Defaults to the input filename.
- `-m, --model`       (optional)  OpenAI model to use. Defaults to `gpt-4o-mini`.
- `-e, --max_edge`    (optional)  Maximum pixel length for the image's longest edge. Defaults to `1024`.

You can view full help:
```bash
uv run poster_summary.py -- -h
```

### Output

After running, the script generates:

1. **Markdown file**: `<prefix>.md`
   - Contains the resized poster embedded at the top.
   - Below it, the GPT-generated summary in markdown.
2. **HTML file**: `summary/<prefix>.html`
   - Styled page with responsive layout.
   - Thumbnail of the resized poster.
   - Click thumbnail to view full-resolution image in a modal.
3. **Resized images**: saved under `summary/resized/` or `<output_dir>/resized/`:
   - `<prefix>_resized.jpg` and/or `.HEIC` as needed.

## Directory Structure

```
poster_summary/
├── poster_summary.py   # Main CLI script
├── .env                # (external) OpenAI API key
└── README.md           # This documentation
```

## Example

```bash
# Analyze a HEIC image and output to 'output/' directory
uv run poster_summary.py -i posters/IMG_1245.HEIC -o output -p my_poster
```

This will create:
- `output/my_poster.md`
- `output/my_poster.html`
- `output/resized/IMG_1245_resized.jpg`

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.