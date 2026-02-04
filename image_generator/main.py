import gradio as gr
import openai
import os
import requests
import json
import base64
from datetime import datetime
from pathlib import Path
from PIL import Image
import io
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Setup logging with loguru
logger.remove()  # Remove default handler
logger.add(
    "logs/image_generator_{time:YYYY-MM-DD}.log",
    rotation="1 week",
    retention="4 weeks",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO"
)
logger.add(
    lambda msg: print(msg, end=""),
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <cyan>{message}</cyan>",
    level="INFO"
)

# Create logs directory if it doesn't exist
Path("logs").mkdir(exist_ok=True)

logger.info("Starting AI Image Generator application")

# Initialize OpenAI client
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# Create images directory if it doesn't exist
IMAGES_DIR = Path("generated_images")
IMAGES_DIR.mkdir(exist_ok=True)

# Cost tracking setup
COSTS_FILE = Path("costs.json")

# Image styles from imagestyles.ai
IMAGE_STYLES = {
    # Basic styles
    "natural": "More natural and less hyper-real",
    "vivid": "Hyper-real and dramatic",
    
    # Digital Art Styles
    "no-mans-sky": "in No Man's Sky video game style",
    "8-bit": "in 8-bit pixel art style",
    "pixel-art": "in pixel art style",
    "pixel-art-chibi": "in pixel art chibi style",
    "voxels": "in voxel art style",
    "low-poly": "in low-poly 3D style",
    "low-poly-isometric-game": "in low-poly isometric game style",
    "3d": "in 3D rendered style",
    "motion-graphics": "in motion graphics style",
    "hud": "in HUD interface style",
    "ascii-art": "in ASCII art style",
    "cel-shading": "in cel-shaded anime style",
    
    # Traditional Art Styles
    "watercolor": "in watercolor painting style",
    "oil-on-canvas": "in oil painting on canvas style",
    "pop-art": "in pop art style",
    "line-drawing": "in line drawing style",
    "minimalistic": "in minimalistic art style",
    "picasso": "in Pablo Picasso cubist style",
    "low-poly-picasso": "in low-poly Picasso cubist style",
    "medieval": "in medieval manuscript style",
    "hieroglyphics": "in ancient Egyptian hieroglyphics style",
    "caricature": "in caricature drawing style",
    "police-sketch": "in police sketch style",
    "coloring-book": "in coloring book line art style",
    "paint-by-number": "in paint by number style",
    "sticker": "in sticker art style",
    "cutout": "in paper cutout collage style",
    "sand": "in sand art style",
    "paint-on-glass": "in paint on glass animation style",
    "drawn-on-film": "in drawn on film animation style",
    "whiteboard": "in whiteboard drawing style",
    
    # Photography Styles
    "polaroid": "in vintage Polaroid photography style",
    "wet-plate-collodion": "in wet plate collodion photography style",
    "western": "in western film photography style",
    
    # Animation Styles - TV Shows
    "anime": "in anime art style",
    "retro-anime": "in retro anime style",
    "manga": "in manga comic style",
    "chibi": "in chibi anime style",
    "studio-ghibli": "in Studio Ghibli animation style",
    "rick-and-morty": "in Rick and Morty animation style",
    "simpsons": "in The Simpsons animation style",
    "south-park": "in South Park animation style",
    "muppets": "in Jim Henson's Muppets style",
    "invader-zim": "in Invader Zim animation style",
    "bobs-burgers": "in Bob's Burgers animation style",
    "king-of-the-hill": "in King of the Hill animation style",
    "spongebob": "in SpongeBob SquarePants animation style",
    "pokemon": "in Pokemon animation style",
    "animal-crossing": "in Animal Crossing game art style",
    "batman-the-animated-series": "in Batman: The Animated Series style",
    "smiling-friends": "in Smiling Friends animation style",
    "power-puff-girls": "in PowerPuff Girls animation style",
    "phineas-and-ferb": "in Phineas and Ferb animation style",
    "rockos-modern-life": "in Rocko's Modern Life animation style",
    "gravity-falls": "in Gravity Falls animation style",
    "ducktales": "in DuckTales animation style",
    "doug": "in Doug animation style",
    "hey-arnold": "in Hey Arnold animation style",
    "rugrats": "in Rugrats animation style",
    "peppa-pig": "in Peppa Pig animation style",
    "ren-and-stimpy": "in Ren and Stimpy animation style",
    "realistic-cartoon": "in realistic cartoon style",
    "cuphead": "in Cuphead game animation style",
    "wallace-and-gromit": "in Wallace and Gromit claymation style",
    "parappa-the-rapper": "in PaRappa the Rapper style",
    "snoopy": "in Snoopy/Peanuts comic style",
    
    # Comic Book Styles
    "classic-comic-book": "in classic comic book style",
    "marvel": "in Marvel Comics style",
    "flat-corporate": "in flat corporate illustration style",
    
    # Gaming Styles
    "grand-theft-auto-v": "in Grand Theft Auto V game style",
    "valorant": "in Valorant game art style",
    "mario-n64": "in Mario 64 game style",
    "fnaf": "in Five Nights at Freddy's style",
    "silent-hill-2": "in Silent Hill 2 game style",
    "monument-valley": "in Monument Valley game style",
    "altos-adventure": "in Alto's Adventure game style",
    "mortal-combat": "in Mortal Kombat game style",
    "monkey-island": "in Monkey Island game style",
    "contra": "in Contra game style",
    "startropics": "in StarTropics game style",
    "mario-bros-3": "in Super Mario Bros 3 style",
    "megaman": "in Mega Man game style",
    "last-of-us": "in The Last of Us game style",
    "hollow-knight": "in Hollow Knight game style",
    
    # 3D Animation & Clay
    "claymation": "in claymation stop-motion style",
    "claymation-voxel": "in claymation voxel art style",
    "rotoscope": "in rotoscoped animation style",
    "chuckimation": "in Chuckimation style",
    "puppetry": "in puppet show style",
    "stuffed-animal": "in stuffed animal toy style",
    "knitted-toy": "in knitted toy style",
    "lego": "in LEGO brick style",
    
    # Special Effects
    "plexus": "in plexus network visualization style",
    "medieval-plexus": "in medieval plexus style",
    "sunset-hills": "in sunset hills landscape style",
    "roman-empire": "in Roman Empire classical style",
}

# OpenAI pricing (as of 2024/2025)
PRICING = {
    "gpt-image-1": {
        "low": {
            "512x512": 0.020,
            "1024x1024": 0.040,
            "2048x2048": 0.080,
            "1792x1024": 0.040,  # 16:9 aspect ratio
            "1024x1792": 0.040,  # 9:16 aspect ratio
        },
        "medium": {
            "512x512": 0.070,
            "1024x1024": 0.140,
            "2048x2048": 0.280,
            "1792x1024": 0.140,  # 16:9 aspect ratio
            "1024x1792": 0.140,  # 9:16 aspect ratio
        },
        "high": {
            "512x512": 0.190,
            "1024x1024": 0.380,
            "2048x2048": 0.720,
            "1792x1024": 0.380,  # 16:9 aspect ratio
            "1024x1792": 0.380,  # 9:16 aspect ratio
        }
    },
    "dall-e-3": {
        "standard": {
            "1024x1024": 0.040,
            "1024x1792": 0.080,
            "1792x1024": 0.080
        },
        "hd": {
            "1024x1024": 0.080,
            "1024x1792": 0.120,
            "1792x1024": 0.120
        }
    },
    "dall-e-2": {
        "standard": {
            "256x256": 0.016,
            "512x512": 0.018,
            "1024x1024": 0.020
        }
    },
    "gpt-4o-mini-vision": 0.002  # Approximate cost per image analysis
}

def load_costs():
    """Load cost tracking data from JSON file."""
    if COSTS_FILE.exists():
        try:
            with open(COSTS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"total_cost": 0.0, "total_images": 0, "sessions": []}
    return {"total_cost": 0.0, "total_images": 0, "sessions": []}

def save_costs(cost_data):
    """Save cost tracking data to JSON file."""
    with open(COSTS_FILE, 'w') as f:
        json.dump(cost_data, f, indent=2)

def calculate_cost(model, quality, size):
    """Calculate the cost for generating an image."""
    try:
        # Map fallback quality for gpt-image-1 if needed
        if model == "gpt-image-1":
            # Accept both 'low', 'medium', 'high' and 'standard', 'hd'
            if quality not in PRICING[model]:
                # Map 'standard'->'low', 'hd'->'medium' (approximate)
                if quality == "standard":
                    mapped_quality = "low"
                elif quality == "hd":
                    mapped_quality = "medium"
                else:
                    mapped_quality = "low"
            else:
                mapped_quality = quality
            return PRICING[model][mapped_quality].get(size, 0.040)
        elif model == "dall-e-2":
            return PRICING[model]["standard"].get(size, 0.020)
        else:  # dall-e-3
            # Accept both 'low', 'medium', 'high' and 'standard', 'hd'
            if quality not in PRICING[model]:
                if quality == "low":
                    mapped_quality = "standard"
                elif quality in ["medium", "high"]:
                    mapped_quality = "hd"
                else:
                    mapped_quality = "standard"
            else:
                mapped_quality = quality
            return PRICING[model][mapped_quality].get(size, 0.040)
    except KeyError:
        logger.warning(f"Price not found for model: {model}, quality: {quality}, size: {size}")
        return 0.040  # Default fallback cost

def update_cost_tracking(model, quality, size, prompt, analysis_cost=0.0):
    """Update the cost tracking with a new image generation."""
    cost_data = load_costs()
    current_cost = calculate_cost(model, quality, size) + analysis_cost
    
    # Update totals
    cost_data["total_cost"] += current_cost
    cost_data["total_images"] += 1
    
    # Add session entry
    session_entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "quality": quality,
        "size": size,
        "generation_cost": calculate_cost(model, quality, size),
        "analysis_cost": analysis_cost,
        "total_cost": current_cost,
        "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt
    }
    
    cost_data["sessions"].append(session_entry)
    
    # Keep only last 1000 sessions to prevent file from growing too large
    if len(cost_data["sessions"]) > 1000:
        cost_data["sessions"] = cost_data["sessions"][-1000:]
    
    save_costs(cost_data)
    
    # Log the cost tracking
    logger.info(f"Cost tracking updated - Model: {model}, Quality: {quality}, Size: {size}, "
               f"Generation Cost: ${calculate_cost(model, quality, size):.3f}, "
               f"Analysis Cost: ${analysis_cost:.3f}, Total: ${current_cost:.3f}")
    
    return current_cost, cost_data["total_cost"]

def update_style_info(style_choice):
    """Update the style information display when style dropdown changes."""
    return IMAGE_STYLES.get(style_choice, "Style information not available")

def encode_image_to_base64(image):
    """Convert PIL Image to base64 string for API."""
    if image is None:
        return None
    
    # Convert to RGB if necessary
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Save to bytes
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=85)
    
    # Encode to base64
    image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return image_base64

def analyze_reference_image(image):
    """Analyze uploaded image using OpenAI's vision model."""
    if image is None:
        logger.info("No reference image provided for analysis")
        return "No reference image provided."
    
    try:
        # Check if API key is set
        if not os.getenv("OPENAI_API_KEY"):
            logger.error("OpenAI API key not found for image analysis")
            return "❌ Error: OpenAI API key not found for image analysis."
        
        # Encode image to base64
        image_base64 = encode_image_to_base64(image)
        if not image_base64:
            logger.error("Failed to process reference image for analysis")
            return "❌ Error: Failed to process reference image."
        
        logger.info("Starting image analysis with GPT-4o-mini vision model")
        
        # Use OpenAI's vision model to analyze the image
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analyze this image and provide a detailed description that could be used as a prompt for AI image generation. Include:
1. Main subjects and objects
2. Visual style, colors, and mood
3. Composition and layout
4. Artistic style or technique
5. Lighting and atmosphere

Provide a concise but comprehensive description suitable for image generation prompts."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        
        analysis = response.choices[0].message.content
        
        # Log the analysis
        logger.info(f"Image analysis completed successfully. Analysis: {analysis[:200]}...")
        
        return f"🔍 Image Analysis:\n{analysis}"
        
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return f"❌ Error analyzing image: {str(e)}"

def combine_prompt_with_analysis(user_prompt, image_analysis, use_reference):
    """Combine user prompt with image analysis if reference is being used."""
    if not use_reference or not image_analysis or image_analysis.startswith("❌") or image_analysis.startswith("No reference"):
        return user_prompt
    
    # Extract just the analysis part (remove the "🔍 Image Analysis:" prefix)
    clean_analysis = image_analysis.replace("🔍 Image Analysis:\n", "").strip()
    
    if user_prompt.strip():
        # User provided a prompt, combine it with analysis
        combined = f"{user_prompt}\n\nReference style and elements: {clean_analysis}"
    else:
        # No user prompt, use analysis as the main prompt
        combined = f"Create an image inspired by: {clean_analysis}"
    
    return combined

def generate_image(prompt, size="1024x1024", quality="low", style="vivid", model="gpt-image-1", reference_image=None, use_reference=False):
    """
    Generate an image from a text prompt using OpenAI's image generation API.
    
    Args:
        prompt (str): Text description of the image to generate
        size (str): Image resolution 
        quality (str): Image quality (low, medium, high for gpt-image-1; standard, hd for dall-e)
        style (str): Image style (vivid, natural)
        model (str): Model to use (gpt-image-1, dall-e-3, dall-e-2)
        reference_image: PIL Image object for reference
        use_reference (bool): Whether to use reference image for analysis
    
    Returns:
        tuple: (PIL Image object, success message, saved file path, cost info) or (None, error message, None, None)
    """
    logger.info(f"Starting image generation - Model: {model}, Size: {size}, Quality: {quality}, Use Reference: {use_reference}")
    logger.info(f"Original prompt: {prompt}")
    
    try:
        # Validate input
        if not prompt or prompt.strip() == "":
            if not use_reference or reference_image is None:
                logger.warning("No prompt provided and no reference image to analyze")
                return None, "❌ Error: Please enter a prompt or upload a reference image.", None, None
        
        # Analyze reference image if provided and requested
        final_prompt = prompt
        analysis_cost = 0.0
        if use_reference and reference_image is not None:
            logger.info("Analyzing reference image")
            image_analysis = analyze_reference_image(reference_image)
            if not image_analysis.startswith("❌"):
                final_prompt = combine_prompt_with_analysis(prompt, image_analysis, use_reference)
                analysis_cost = PRICING["gpt-4o-mini-vision"]  # Add analysis cost
                logger.info(f"Reference analysis completed. Final prompt: {final_prompt}")
            else:
                logger.error(f"Reference image analysis failed: {image_analysis}")
                return None, f"❌ Error with reference image: {image_analysis}", None, None
        
        # Apply style enhancement to the prompt
        if style in IMAGE_STYLES and style not in ["vivid", "natural"]:
            style_prompt = IMAGE_STYLES[style]
            if style_prompt and not style_prompt.startswith("More") and not style_prompt.startswith("Hyper"):
                final_prompt = f"{final_prompt} {style_prompt}"
                logger.info(f"Applied style '{style}' to prompt: {style_prompt}")
        
        if len(final_prompt.strip()) < 3:
            logger.warning("Final prompt is too short")
            return None, "❌ Error: Prompt is too short. Please provide a more detailed description.", None, None
        
        # Check if API key is set
        if not os.getenv("OPENAI_API_KEY"):
            logger.error("OpenAI API key not found")
            return None, "❌ Error: OpenAI API key not found. Please set OPENAI_API_KEY environment variable.", None, None
        
        # Handle different models and validate compatibility
        actual_model = model
        if model == "gpt-image-1":
            # For now, use dall-e-3 as fallback until gpt-image-1 is available
            actual_model = "dall-e-3"
            # Map quality levels
            if quality == "low":
                quality = "standard"
            elif quality in ["medium", "high"]:
                quality = "hd"
            logger.info(f"Using DALL-E 3 as fallback for GPT-Image-1. Mapped quality: {quality}")
        
        # Validate model and size compatibility
        if actual_model == "dall-e-2":
            if size not in ["256x256", "512x512", "1024x1024"]:
                size = "1024x1024"  # Default to supported size
                logger.info(f"Adjusted size to {size} for DALL-E 2 compatibility")
            if quality == "hd":
                quality = "standard"  # DALL-E 2 doesn't support HD
                logger.info("Adjusted quality to standard for DALL-E 2 compatibility")
        
        # Calculate cost before generation
        estimated_cost = calculate_cost(model, quality if model == "gpt-image-1" else quality, size)
        logger.info(f"Estimated cost: ${estimated_cost:.3f}")
        
        # Generate image
        generate_params = {
            "model": actual_model,
            "prompt": final_prompt.strip(),
            "size": size,
            "n": 1
        }
        
        # Add quality and style for DALL-E 3
        if actual_model == "dall-e-3":
            generate_params["quality"] = quality
            generate_params["style"] = style
        
        logger.info(f"Calling OpenAI API with params: {generate_params}")
        response = client.images.generate(**generate_params)
        
        # Get the image URL
        image_url = response.data[0].url
        logger.info(f"Image generated successfully. URL received: {image_url[:50]}...")
        
        # Download the image
        image_response = requests.get(image_url, timeout=30)
        image_response.raise_for_status()
        
        # Convert to PIL Image
        image = Image.open(io.BytesIO(image_response.content))
        logger.info(f"Image downloaded and converted to PIL format. Size: {image.size}")
        
        # Save the image locally
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = "".join(c for c in prompt[:50] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_prompt = "_".join(safe_prompt.split())
        ref_suffix = "_ref" if use_reference else ""
        filename = f"{timestamp}_{model}_{safe_prompt}{ref_suffix}.png"
        filepath = IMAGES_DIR / filename
        
        image.save(filepath, "PNG")
        logger.info(f"Image saved to: {filepath}")
        
        # Update cost tracking (use original prompt for tracking)
        current_cost, total_cost = update_cost_tracking(model, quality if model == "gpt-image-1" else quality, size, prompt, analysis_cost)
        
        success_msg = f"✅ Image generated successfully!\n📁 Saved as: {filepath}"
        if use_reference:
            success_msg += "\n🔍 Used reference image analysis"
        
        cost_breakdown = f"💰 Generation: ${calculate_cost(model, quality if model == 'gpt-image-1' else quality, size):.3f}"
        if analysis_cost > 0:
            cost_breakdown += f" + Analysis: ${analysis_cost:.3f}"
        cost_info = f"{cost_breakdown} = Total: ${current_cost:.3f} | Total spent: ${total_cost:.2f}"
        
        logger.info(f"Image generation completed successfully. Total cost: ${current_cost:.3f}")
        return image, success_msg, str(filepath), cost_info
        
    except openai.APIError as e:
        error_msg = f"❌ OpenAI API Error: {str(e)}"
        logger.error(f"OpenAI API Error: {str(e)}")
        return None, error_msg, None, None
    except requests.RequestException as e:
        error_msg = f"❌ Network Error: Failed to download image. {str(e)}"
        logger.error(f"Network error during image download: {str(e)}")
        return None, error_msg, None, None
    except Exception as e:
        error_msg = f"❌ Unexpected Error: {str(e)}"
        logger.error(f"Unexpected error during image generation: {str(e)}")
        return None, error_msg, None, None

def clear_inputs():
    """Clear all inputs and outputs."""
    return "", "1024x1024", "low", "vivid", "gpt-image-1", None, False, None, "", "", "", "", IMAGE_STYLES["vivid"]

def generate_image_with_summary_update(prompt, size="1024x1024", quality="low", style="vivid", model="gpt-image-1", reference_image=None, use_reference=False):
    """Generate image and return updated cost summary."""
    image, status, filepath, cost_info = generate_image(prompt, size, quality, style, model, reference_image, use_reference)
    updated_summary = get_cost_summary()
    return image, status, filepath, cost_info, updated_summary

def analyze_uploaded_image(image):
    """Analyze uploaded image and return analysis."""
    if image is None:
        return "No image uploaded."
    return analyze_reference_image(image)

def get_cost_summary():
    """Get a summary of current costs."""
    cost_data = load_costs()
    return f"💰 Total Images: {cost_data['total_images']} | Total Cost: ${cost_data['total_cost']:.2f}"

def update_interface_for_model(model):
    """Update interface elements based on selected model."""
    if model == "gpt-image-1":
        # GPT-Image-1 supported sizes and qualities
        size_choices = ["512x512", "1024x1024", "2048x2048", "1792x1024", "1024x1792"]
        size_value = "1024x1024"
        quality_choices = ["low", "medium", "high"]
        quality_value = "low"
        info_text = "GPT-Image-1: Supports all sizes including 16:9 ratios. Low/Medium/High quality."
    elif model == "dall-e-2":
        # DALL-E 2 supported sizes
        size_choices = ["256x256", "512x512", "1024x1024"]
        size_value = "1024x1024"
        quality_choices = ["standard"]
        quality_value = "standard"
        info_text = "DALL-E 2: Supports 256x256, 512x512, 1024x1024. Standard quality only."
    else:  # dall-e-3
        size_choices = ["1024x1024", "1024x1792", "1792x1024"]
        size_value = "1024x1024"
        quality_choices = ["standard", "hd"]
        quality_value = "standard"
        info_text = "DALL-E 3: Supports 1024x1024, 1024x1792, 1792x1024. Standard and HD quality."
    
    return (
        gr.Dropdown(choices=size_choices, value=size_value),
        gr.Dropdown(choices=quality_choices, value=quality_value),
        info_text
    )

def create_interface():
    """Create and configure the Gradio interface."""
    
    with gr.Blocks(
        title="AI Image Generator",
        theme=gr.themes.Soft(),
        css="""
        .container { max-width: 800px; margin: auto; }
        .title { text-align: center; color: #2563eb; margin-bottom: 20px; }
        .description { text-align: center; color: #64748b; margin-bottom: 30px; }
        """
    ) as demo:
        
        gr.HTML("""
        <div class="container">
            <h1 class="title">🎨 AI Image Generator</h1>
            <p class="description">Generate stunning images from text descriptions using OpenAI's DALL·E API</p>
            <p class="description">💡 <strong>New:</strong> Upload a reference image for AI analysis and style transfer!</p>
        </div>
        """)
        
        # Cost summary
        with gr.Row():
            cost_summary = gr.Textbox(
                label="💰 Cost Summary",
                value=get_cost_summary(),
                interactive=False,
                show_label=True
            )
        
        with gr.Row():
            with gr.Column(scale=1):
                # Input controls
                with gr.Group():
                    gr.Markdown("### 📝 Image Settings")
                    
                    prompt_input = gr.Textbox(
                        label="Image Prompt",
                        placeholder="Describe the image you want to generate (e.g., 'a cat riding a motorcycle in space')",
                        lines=3,
                        max_lines=5
                    )
                    
                    # Reference image section
                    with gr.Group():
                        gr.Markdown("#### 🖼️ Reference Image (Optional)")
                        
                        with gr.Row():
                            reference_image = gr.Image(
                                label="Upload Reference Image",
                                type="pil",
                                height=200,
                                show_download_button=False
                            )
                            
                            with gr.Column():
                                use_reference_checkbox = gr.Checkbox(
                                    label="Use Reference Image",
                                    value=False,
                                    info="Analyze reference image and incorporate into prompt"
                                )
                                
                                analyze_btn = gr.Button(
                                    "🔍 Analyze Image",
                                    variant="secondary",
                                    size="sm"
                                )
                        
                        image_analysis_output = gr.Textbox(
                            label="Image Analysis",
                            placeholder="Upload an image and click 'Analyze Image' to see AI analysis...",
                            lines=4,
                            max_lines=6,
                            interactive=False
                        )
                    
                    with gr.Row():
                        size_dropdown = gr.Dropdown(
                            choices=["512x512", "1024x1024", "2048x2048", "1792x1024", "1024x1792"],
                            value="1024x1024",
                            label="Image Size",
                            info="Resolution of the generated image (16:9 ratios available)"
                        )
                        
                        quality_dropdown = gr.Dropdown(
                            choices=["low", "medium", "high"],
                            value="low",
                            label="Quality",
                            info="Image quality (higher quality costs more)"
                        )

                        model_dropdown = gr.Dropdown(
                            choices=["gpt-image-1", "dall-e-3", "dall-e-2"],
                            value="gpt-image-1",
                            label="Model",
                            info="Select the image generation model"
                        )

                    style_dropdown = gr.Dropdown(
                        choices=list(IMAGE_STYLES.keys()),
                        value="vivid",
                        label="🎨 Art Style",
                        info="Choose from 80+ artistic styles - see https://imagestyles.ai for examples"
                    )
                    
                    # Style preview and info
                    style_info = gr.Textbox(
                        value=IMAGE_STYLES["vivid"],
                        label="Style Description",
                        interactive=False,
                        max_lines=2
                    )
                    
                    style_link = gr.HTML(
                        value='<p style="text-align: center; margin: 5px 0;"><a href="https://imagestyles.ai" target="_blank" style="color: #3498db; text-decoration: none;">🔗 View All Styles with Examples at imagestyles.ai</a></p>'
                    )
                
                # Action buttons
                with gr.Row():
                    generate_btn = gr.Button(
                        "🎨 Generate Image",
                        variant="primary",
                        size="lg"
                    )
                    clear_btn = gr.Button(
                        "🗑️ Clear",
                        variant="secondary",
                        size="lg"
                    )
            
            with gr.Column(scale=1):
                # Output section
                with gr.Group():
                    gr.Markdown("### 🖼️ Generated Image")
                    
                    output_image = gr.Image(
                        label="Generated Image",
                        type="pil",
                        height=400,
                        show_download_button=True
                    )
                    
                    status_text = gr.Textbox(
                        label="Status",
                        interactive=False,
                        max_lines=3
                    )
                    
                    cost_text = gr.Textbox(
                        label="Cost Information",
                        interactive=False,
                        max_lines=2
                    )
                    
                    filepath_text = gr.Textbox(
                        label="Saved File Path",
                        interactive=False,
                        visible=False
                    )
        
        # Examples section
        with gr.Row():
            gr.Examples(
                examples=[
                    ["a majestic lion wearing a crown in a magical forest"],
                    ["a futuristic city floating in the clouds at sunset"],
                    ["a cozy coffee shop in a treehouse with fairy lights"],
                    ["a robot playing chess with a cat in a library"],
                    ["an underwater palace made of coral and pearls"],
                    ["a steampunk airship flying over mountains"],
                ],
                inputs=[prompt_input],
                label="💡 Example Prompts"
            )
        
        # Event handlers
        generate_btn.click(
            fn=generate_image_with_summary_update,
            inputs=[prompt_input, size_dropdown, quality_dropdown, style_dropdown, model_dropdown, reference_image, use_reference_checkbox],
            outputs=[output_image, status_text, filepath_text, cost_text, cost_summary]
        )
        
        analyze_btn.click(
            fn=analyze_uploaded_image,
            inputs=[reference_image],
            outputs=[image_analysis_output]
        )
        
        clear_btn.click(
            fn=clear_inputs,
            outputs=[prompt_input, size_dropdown, quality_dropdown, style_dropdown, model_dropdown,
                    reference_image, use_reference_checkbox, output_image, status_text, filepath_text, cost_text, image_analysis_output, style_info]
        )
        
        # Style dropdown change handler
        style_dropdown.change(
            fn=update_style_info,
            inputs=[style_dropdown],
            outputs=[style_info]
        )
        
        # Enter key handler for prompt input
        prompt_input.submit(
            fn=generate_image_with_summary_update,
            inputs=[prompt_input, size_dropdown, quality_dropdown, style_dropdown, model_dropdown, reference_image, use_reference_checkbox],
            outputs=[output_image, status_text, filepath_text, cost_text, cost_summary]
        )
    
    return demo

def main():
    """Main function to run the application."""
    
    logger.info("Initializing AI Image Generator main application")
    
    # Check if API key is available
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY environment variable not found")
        print("⚠️  Warning: OPENAI_API_KEY environment variable not found!")
        print("Please set your OpenAI API key in a .env file or as an environment variable.")
        print("Example: echo 'OPENAI_API_KEY=your-api-key-here' > .env")
        print("\nThe app will still start, but image generation will fail without a valid API key.\n")
    else:
        logger.info("OpenAI API key found and loaded")
    
    # Create and launch the interface
    demo = create_interface()
    
    logger.info("Created Gradio interface")
    print("🚀 Starting AI Image Generator...")
    print("📁 Generated images will be saved to:", IMAGES_DIR.absolute())
    print("📝 Logs will be saved to: logs/ directory")
    
    logger.info(f"Starting Gradio server on port 7860")
    logger.info(f"Images will be saved to: {IMAGES_DIR.absolute()}")
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        # show_tips=True,
        inbrowser=True
    )

if __name__ == "__main__":
    main()