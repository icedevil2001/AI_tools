# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "click",
#     "google-genai",
#     "openai",
#     "python-dotenv",
#     "markdown",     
#     "pillow",       
#     "pillow-heif",  
# ]
# ///

from pathlib import Path
import base64 
from PIL import Image  
import pillow_heif 
pillow_heif.register_heif_opener()
from dataclasses import dataclass
import click
from dotenv import load_dotenv
import os
from openai import OpenAI
import markdown  
import re 



## https://platform.openai.com/docs/guides/images-vision?api-mode=responses&format=base64-encoded#gpt-4-1-mini-gpt-4-1-nano-o4-mini 
#  https://ai.google.dev/gemini-api/docs/image-understanding 

## markdown: https://python-markdown.github.io/reference/ 



# system_prompt = """

# # <<Title>>

# ## 1. Summary
# - Give a high-level overview of the poster’s scope and purpose.
# - Break down the main sections or figures and summarize key points.

# ## 2. Impact
# - Explain the significance of the poster’s message or findings.
# - Discuss potential applications, audience, or broader relevance.

# ## 3. Limitations
# - Identify any weaknesses or gaps in content or presentation.
# - Suggest areas for improvement or future work.

# ## 4. Main Takeaway
# - State the single most important insight the viewer should remember.

# ## 5. Keywords
# - List 5–10 concise, relevant keywords or phrases.

# ### Response Guidelines
# - Use Markdown headings, bullet lists, and concise language.
# - Do not include extraneous commentary or code.
# - Ensure each section is clearly labeled and self-contained.
# """


# ### poster contents
# extract all text from the poster image and include it in the report and include all sections from poster 


system_prompt = """
You are an expert at analyzing scientific or academic posters. Given a poster image, generate a clear, concise, and well-structured markdown report. Automatically extract and insert the title in place of <<Title>>.

# <<Title>> 

## Main Takeaway
Identify the single most important message or piece of information conveyed by the poster.

## Summary
Provide a detailed and extensive summary of the poster's content, scope, and purpose.

### High-Level Overview: 
Describe the main topic and objectives of the poster.

### Main Sections: 
- Identify and summarize the main sections or figures of the poster.
- Describe any important visual elements, such as graphs, charts, tables, or images, and their significance.

## Impact
Describe the significance of the poster's content and its potential impact on the field or audience.

## Short commings 
Describe any limitations or shortcomings of the poster's content, including areas for improvement or further research.

## Keywords
List relevant keywords that describe the poster's topic and content.


# Output Format

- Use markdown format for your response.
- Summarize each section clearly and concisely.
- Extract the title from the poster and replace <<Title>> with title from poster
"""



env_path = Path(".env")
if env_path.exists():
    print(f"Loading environment variables from {env_path}")
    load_dotenv(env_path)
else:
    print(
        "No .env file found. Please enter your OpenAI API key—it will be kept in memory for this session only and discarded when the script exits. "
        "To store your key permanently, create a .env file alongside this script containing:\n"
        "OPENAI_API_KEY=<your_key>"
    )
    key_input = click.prompt("OpenAI API Key", hide_input=True)
    os.environ["OPENAI_API_KEY"] = key_input
    # raise FileNotFoundError(f"File {env_path} does not exist.")

# api_key = os.getenv("GOOGLE_API_KEY")
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("API key not found. Please set the OPENAI_API_KEY environment variable.")
print(f"API Key: {api_key[:4]}***{api_key[-4:]}")  

# client = genai.Client(api_key=api_key)
# client = openai.Client(api_key=api_key)

client = OpenAI(api_key=api_key)



class Img: 
    def __init__(self, image_path: str):
        self.image_path = Path(image_path)
        if not self.image_path.exists():
            raise FileNotFoundError(f"File {self.image_path} does not exist.")
        self.image_path = self.image_path  if self.image_path.suffix.lower() == ".jpg" else self.convert_to_jpg()
        
        
    def convert_to_jpg(self):
        # Convert HEIC or other formats to JPEG via Pillow
        jpg_filepath = self.image_path.with_suffix('.jpg')
        img = Image.open(self.image_path)
        img = img.convert('RGB')
        img.save(jpg_filepath, 'JPEG')
        return jpg_filepath
    
    def encode_image(self):
        """Encode the image to base64 format."""
        with open(self.image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
        
    def resize_image(self, max_edge: int = 1024):
        """
        Resize the image so that its longest edge is max_edge pixels.
        Saves the resized image into the 'summary' folder and returns its Path.
        """
        img = Image.open(self.image_path)
        width, height = img.size
        ratio = max_edge / max(width, height)
        if ratio < 1:
            new_size = (int(width * ratio), int(height * ratio))
            # Use LANCZOS filter for high-quality downsampling
            img = img.resize(new_size)
            img.save(self.image_path)
        else:
            resized_path = self.image_path
        return resized_path
    

@dataclass
class Poster:
    image_path: Path
    summary: str = ""
    
    def __post_init__(self):
        
        if not self.image_path.exists():
            raise FileNotFoundError(f"File {self.image_path} does not exist.")
        self.image_path = self.image_path  if self.image_path.suffix.lower() == ".jpg" else self.convert_to_jpg()
        
    @property        
    def encode_image(self):
        """Encode the image to base64 format."""
        with open(self.image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def add_summary(self, summary):
        """markdown format"""
        self.summary = summary
        
    @property
    def title(self):
        """Extract the title from the image filename."""
        if self.summary:
            return self.summary.split("\n", maxsplit=1)[0].strip().replace("#", "").strip()
        return self.image_path.stem
        
    def convert_to_jpg(self):
        jpg_filepath = self.image_path.with_suffix('.jpg')
        img = Image.open(self.image_path)
        img = img.convert('RGB')
        img.save(jpg_filepath, 'JPEG')
        return jpg_filepath
    
def resize_image(image_path, max_edge: int = 1024, resized_path: Path = None) -> Path:
    """
    Resize the image so that its longest edge is max_edge pixels.
    Saves the resized image into the 'summary' folder and returns its Path.
    """
    img = Image.open(image_path)
    width, height = img.size
    ratio = max_edge / max(width, height)
    if ratio < 1:
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size)
        img.save(resized_path)
    else:
        resized_path = image_path
    return resized_path
    
    
    # def convert_heic_to_jpg(self, heic_filepath: Path, jpg_filepath: Path):
    #     """
    #     Convert HEIC image to JPEG format using Pillow.
    #     """
    #     img = Image.open(heic_filepath)
    #     img = img.convert('RGB')
    #     img.save(jpg_filepath, 'JPEG')
    #     print(f"Converted {heic_filepath} to {jpg_filepath}")
    #     return jpg_filepath
        

# client = OpenAI()

# response = client.responses.create(
#     model="gpt-4.1-nano",
#     input=[
#         {
#             "role": "system",
#             "content": [
#                 {
#                     "type": "input_text",
#                     "text": "Please analyze this poster image and provide the following information in markdown format:\n\n## Detailed Summary\nProvide a comprehensive summary of the poster's content.\n\n## Main Takeaway\nWhat is the single most important message or piece of information conveyed by the poster?\n\n## Keywords\nList relevant keywords that describe the poster's topic and content\n",
#                 }
#             ],
#         },
#         {
#             "id": "msg_681a556d36988192b73da03d5417fe900ad016031f9680d6",
#             "role": "assistant",
#             "content": [
#                 {
#                     "type": "output_text",
#                     "text": "## Detailed Summary\nThe poster presents an illustrative and educational overview of a biological or medical topic, likely focusing on cellular or molecular processes. It features various diagrams and labeled illustrations highlighting different components, such as cellular structures, pathways, or mechanisms. The visual elements are organized to guide viewers through a step-by-step explanation of a specific process, emphasizing key points with annotations. The overall design aims to inform viewers about complex biological interactions or functions in a clear and accessible manner, possibly targeting students or professionals in science or healthcare fields.\n\n## Main Takeaway\nThe poster aims to elucidate a specific biological process or mechanism, providing insights into how cellular components interact or function within a system, ultimately enhancing understanding of the topic.\n\n## Keywords\n- Cell biology\n- Biological mechanism\n- Molecular pathway\n- Cellular structures\n- Illustration\n- Education\n- Science communication\n- Anatomy",
#                 }
#             ],
#         },
#     ],
#     text={"format": {"type": "text"}},
#     reasoning={},
#     tools=[],
#     temperature=1,
#     max_output_tokens=2048,
#     top_p=1,
#     store=True,
# )



# def convert_folder_heic_to_jpg(folder_path):
#     for filename in os.listdir(folder_path):
#         if filename.lower().endswith((".heic", ".heif")):
#             heic_filepath = os.path.join(folder_path, filename)
#             jpg_filename = os.path.splitext(filename)[0] + ".jpg"
#             jpg_filepath = os.path.join(folder_path, jpg_filename)
#             convert_heic_to_jpg(heic_filepath, jpg_filepath)


# html_template = """
# <!DOCTYPE html>
# <html lang="en">
# <head>

#     <meta charset="utf-8">
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     <title>Poster Summary</title>
# </head>
# <body>
#     <h1>Poster Summary</h1>
#     <img src="data:image/jpeg;base64,{encoded_img}" alt="Poster Image" />
#     <div id="content">{html_body}</div>
# </body>
# </html>
# """

def sanitize_title(title: str) -> str:
    """
    Sanitize the title by removing special characters and replacing spaces with underscores.
    """
    # Remove special characters and replace spaces with underscores
    sanitized_title = re.sub(r'[^\w\s]+', '', title)
    sanitized_title = re.sub(r'[:\'\"]+', '', sanitized_title)
    sanitized_title = re.sub(r'\s+', '_', sanitized_title)
    return sanitized_title


def generate_poster_summary(openai_client: OpenAI, poster: Poster, model="gpt-4o-mini") -> str:
    """
    Generate a detailed summary of the poster image.

    Args:
        openai_client: OpenAI client
        poster: Poster object containing the image path
        model: OpenAI model to use (default: gpt-4o-mini)

    Returns:
        Generated summary text
    """
    
    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": "Please analyze this poster image and provide structured insights following the guidelines above.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{poster.encode_image}"
                        }
                    }
                ],
            }
        ]
    )
    # print(f"Response: {response}")
    poster.summary = response.choices[0].message.content 
    # print(f"Response: {poster.summary}")
    return response


def write_to_markdown(poster: Poster, output_path: str):
    """
    Write the poster summary to a markdown file.
    """
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"![Poster Image]({poster.image_path.as_posix()})\n\n")
        f.write(poster.summary)
    return True



def write_to_html(poster: Poster, full_image_path: Path, html_path: str) -> bool:
    """
    Write the poster image and summary to a standalone HTML file.
    """
    try:
        html_body = markdown.markdown(poster.summary.split("\n", maxsplit=1)[1].strip())
        encoded_thumb = poster.encode_image
        with open(full_image_path, 'rb') as f:
            encoded_full = base64.b64encode(f.read()).decode('utf-8')
        title = poster.title
        html_content = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }}
    h1, h2, h3 {{ color: #333; }}
    img {{ max-width: 100%; height: auto; cursor: pointer; transition: transform 0.3s ease; }}
    /* Modal styles */
    #modal {{ display: none; position: fixed; z-index: 1000; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; }}
    #modal img {{ max-width: 90%; max-height: 90%; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div>
    <img id=\"poster-img\" src=\"data:image/jpeg;base64,{encoded_thumb}\" alt=\"Poster Image\" />
  </div>
  <div id=\"content\">{html_body}</div>
  <!-- Modal for full-size image -->
  <div id=\"modal\" onclick=\"this.style.display='none'\">
    <img src=\"data:image/jpeg;base64,{encoded_full}\" alt=\"Poster Image Enlarged\" />
  </div>
  <script>
    document.getElementById('poster-img').addEventListener('click', function() {{
      document.getElementById('modal').style.display = 'flex';
    }});
  </script>
</body>
</html>"""
        html_file = Path(html_path)
        html_file.parent.mkdir(parents=True, exist_ok=True)
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        return True
    except Exception as e:
        print(f"Error writing HTML: {e}")
        return False



@click.command(context_settings=dict(
    help_option_names=["-h", "--help"],
    show_default=True)
    )
@click.option("--image_path", "-i",
    required=True, 
    # default="/Users/priyesh.rughani/git/AI_tools/poster_summary/posters/IMG_1245.jpeg", 
    help="Path to the poster image file.")

@click.option(
    "--output_dir", "-o",
    default=None,
    help="Output markdown file path. Defaults to image filename with .md extension.",
)

@click.option(
    "--prefix", "-p",
    default=None,
    help="Prefix for the output markdown file name. Defaults to image filename.",
)
@click.option(
    "--model", "-m",
    default="gpt-4o-mini", 
    help="OpenAI model to use for analysis."
    
)
@click.option(
    "--max_edge", "-e",
    default=1024,
    help="Maximum edge length for resizing the image. Default is 1024 pixels."
)
def main(image_path: str = None, output_dir: str = None, model: str = "gpt-4o-mini", prefix: str = None, max_edge: int = 1024):
    """Analyze a poster image and generate a detailed summary."""


    orig_path = Path(image_path)
    if not output_dir:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory created: {output_dir}")
    
    resized_path = (
        output_dir / "resized" / f"{orig_path.stem}_resized{orig_path.suffix}"
    )
    if not (output_dir / "resized").exists(): 
        (output_dir / "resized").mkdir(parents=True, exist_ok=True)
        print(f"Resized directory created: {(output_dir / 'resized')}")

    resized_path = resize_image(image_path, max_edge=max_edge, resized_path=resized_path)
    # raise ValueError("Testing image resize and conversion to jpg")

    poster = Poster(resized_path)

    print(f"🧐 Analyzing poster: {image_path}")
    print(f"🤖 Using model: {model}")


    generate_poster_summary(client, poster, model)
    if prefix == None:
        # prefix = orig_path.stem
        # prefix = poster.title.replace(" ", "_").replace("/", "_").replace("\\", "_")
        prefix = poster.title
        prefix = sanitize_title(prefix)
        
    output_path = Path(output_dir) / f"{prefix}.md"

    if write_to_markdown(poster, output_path):
        print(f"✅ Summary successfully written to {output_path}")
    if write_to_html(poster, orig_path, output_path.with_suffix(".html")):
        print(f"✅ HTML successfully written to {output_path.with_suffix('.html')}")




if __name__ == "__main__":
    main()