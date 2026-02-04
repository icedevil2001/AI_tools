# 🎨 AI Image Generator

An interactive web application that generates images from text descriptions using OpenAI's DALL·E API and Gradio.

## ✨ Features

- **GPT-Image-1 Integration**: Latest image generation model with superior quality (default)
- **98+ Art Styles**: Complete collection from [imagestyles.ai](https://imagestyles.ai) with live previews
- **16:9 Aspect Ratio Support**: Perfect for widescreen and mobile content
- **Interactive Web Interface**: User-friendly Gradio interface with style previews
- **Text-to-Image Generation**: Convert text prompts into stunning images with artistic styles
- **Reference Image Analysis**: Upload images for AI-powered style and content analysis
- **Smart Prompt Enhancement**: Combine your prompts with reference image analysis and art styles
- **Multiple AI Models**: Support for GPT-Image-1, DALL-E 3, and DALL-E 2
- **Flexible Quality Settings**: Low/Medium/High for GPT-Image-1, Standard/HD for DALL-E
- **Comprehensive Logging**: Detailed session logs with weekly rotation
- **Advanced Cost Tracking**: Separate tracking for generation and analysis costs
- **Local Image Saving**: Automatically saves generated images locally
- **Error Handling**: Graceful error handling with informative messages
- **Example Prompts**: Pre-loaded examples to get you started
- **Real-time Status**: Live updates on generation progress

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- UV package manager
- OpenAI API key

### Installation

1. **Clone or navigate to the project directory**:
   ```bash
   cd /Users/pri/git/AI_tools/image_generator
   ```

2. **Install dependencies using UV**:
   ```bash
   uv sync
   ```

3. **Set up your OpenAI API key**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

4. **Run the application**:
   ```bash
   uv run python main.py
   ```

The web interface will automatically open in your browser at `http://localhost:7860`

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root with:

```env
OPENAI_API_KEY=your-openai-api-key-here
```

### API Key Setup

1. Visit [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Create a new API key
3. Add it to your `.env` file

## 🎯 Usage

1. **Enter a Prompt**: Describe the image you want to generate
2. **Choose Art Style**: Select from 98+ artistic styles including:
   - 🎮 Gaming: Pokemon, Mario, Valorant, Grand Theft Auto V
   - 📺 Animation: Studio Ghibli, Rick and Morty, Simpsons, Anime
   - 🎨 Art: Watercolor, Oil Painting, Picasso, Pop Art
   - 🎪 Digital: 8-bit, Pixel Art, Voxel, LEGO, Claymation
   - 📸 Photography: Polaroid, Wet Plate, Western Film
   - *[View all styles with examples at imagestyles.ai](https://imagestyles.ai)*
3. **Upload Reference Image** (Optional):
   - Upload an image for style/content reference
   - Click "Analyze Image" to see AI analysis
   - Check "Use Reference Image" to incorporate analysis
4. **Choose Settings**:
   - **Model**: GPT-Image-1 (default), DALL-E 3, or DALL-E 2
   - **Size**: Various resolutions including 16:9 aspect ratios
   - **Quality**: Low/Medium/High (GPT-Image-1) or Standard/HD (DALL-E)
5. **Generate**: Click "Generate Image" or press Enter
6. **View & Save**: The image appears in the interface and is automatically saved locally

### Art Style Workflow

1. **Browse**: Select any of the 98+ styles from the dropdown
2. **Preview**: Watch the style description update automatically
3. **Apply**: Your prompt gets enhanced with the style (e.g., "in Studio Ghibli animation style")
4. **Generate**: Create images with professional artistic styles

### Style Categories

- **🎮 Gaming**: Grand Theft Auto V, Valorant, Mario 64, Pokemon, Animal Crossing, Hollow Knight
- **📺 Animation**: Studio Ghibli, Rick and Morty, Simpsons, South Park, Anime, Manga
- **🎨 Traditional Art**: Watercolor, Oil on Canvas, Pop Art, Picasso, Minimalistic
- **🎪 Digital Effects**: 8-bit, Pixel Art, Voxel, Low-poly, 3D, Claymation, LEGO
- **📸 Photography**: Polaroid, Wet Plate Collodion, Western Film
- **📚 Comic/Cartoon**: Marvel, Classic Comic Book, Caricature, Line Drawing

### Reference Image Workflow

1. **Upload**: Add your reference image
2. **Analyze**: Click "Analyze Image" to get AI description
3. **Enable**: Check "Use Reference Image" 
4. **Combine**: Your prompt + AI analysis = enhanced generation
5. **Generate**: Create images with reference-based styling

### Example Use Cases

- **Style Transfer**: Upload Van Gogh painting → Generate "modern cityscape" in Van Gogh style
- **Game Art**: Choose "pokemon" style → Generate new creatures in Pokemon animation style
- **Film Aesthetics**: Select "studio-ghibli" → Create magical landscapes in Ghibli style
- **Retro Gaming**: Pick "8-bit" → Generate classic arcade-style artwork
- **Photography**: Use "polaroid" → Create vintage instant camera aesthetics
- **Architecture**: Upload building photo → Generate variations with similar design elements  
- **Character Design**: Upload character art → Generate new characters with similar aesthetics
- **Mixed Media**: Combine "claymation" + reference image → Unique stop-motion style art

### Example Prompts with Styles

- **Studio Ghibli**: "a floating castle in the clouds" → magical Miyazaki-style artwork
- **8-bit**: "a dragon breathing fire" → retro video game pixel art
- **Watercolor**: "a peaceful mountain lake" → soft, flowing paint effects
- **LEGO**: "a space station" → blocky, toy-like construction aesthetic
- **Pokemon**: "a cute electric mouse" → anime-style creature design

## 📁 File Structure

```
image_generator/
├── main.py              # Main application file
├── demo_styles.py       # Demo script showing all 98+ styles
├── pyproject.toml       # Project dependencies
├── .env.example         # Environment variables template
├── .env                 # Your API keys (create this)
├── README.md           # This file
└── generated_images/   # Saved images (created automatically)
```

- Logs contain prompts and responses for debugging but are stored locally

## 📁 File Structure

```
image_generator/
├── main.py              # Main application file
├── pyproject.toml       # Project dependencies
├── .env.example         # Environment variables template
├── .env                 # Your API keys (create this)
├── README.md           # This file
├── logs/               # Application logs (auto-created)
├── generated_images/   # Saved images (auto-created)
└── costs.json         # Cost tracking data (auto-created)
```

## 🎨 Art Styles Collection

This application includes the complete collection of 98+ artistic styles from [imagestyles.ai](https://imagestyles.ai), featuring:

### 🎮 Gaming & Entertainment (25+ styles)
- Classic games: Mario 64, Pokemon, Animal Crossing, Mega Man
- Modern games: Valorant, Grand Theft Auto V, Hollow Knight, Monument Valley
- Retro gaming: 8-bit, pixel art, arcade styles

### 📺 Animation & Cartoons (30+ styles)  
- Japanese animation: Studio Ghibli, Anime, Manga, Chibi
- Western cartoons: Rick and Morty, Simpsons, South Park, Muppets
- Classic animation: Disney, Warner Bros, Hanna-Barbera styles

### 🎨 Traditional Art (20+ styles)
- Fine art: Watercolor, Oil painting, Picasso, Pop art
- Drawing: Line art, Caricature, Police sketch, Minimalistic
- Printmaking: Woodcut, Lithograph, Screen print effects

### 🎪 Digital & 3D (15+ styles)
- 3D rendering: Low-poly, Voxel, LEGO, Claymation
- Digital effects: Motion graphics, HUD, ASCII art
- Modern techniques: Cel-shading, Rotoscope animation

### 📸 Photography (8+ styles)
- Vintage: Polaroid, Wet plate collodion, Film photography
- Cinematic: Western film, Documentary, Portrait styles

**🔗 Browse all styles with visual examples: [imagestyles.ai](https://imagestyles.ai)**

## 🛠️ Dependencies

- **gradio**: Web interface framework
- **openai**: OpenAI API client
- **pillow**: Image processing
- **requests**: HTTP requests
- **python-dotenv**: Environment variable loading

## 🚨 Error Handling

The application handles various error scenarios:

- **Missing API Key**: Clear instructions to set up the key
- **Empty Prompts**: Validation for meaningful input
- **API Errors**: OpenAI service issues
- **Network Issues**: Connection problems
- **File Saving**: Local storage failures

## 💡 Tips

- **Detailed Prompts**: More specific descriptions yield better results
- **HD Quality**: Better quality but costs more credits
- **Vivid Style**: More dramatic and hyper-real images
- **Natural Style**: More realistic and natural-looking images

## 📋 Requirements

- Active OpenAI account with API access
- Sufficient API credits for image generation
- Internet connection for API calls

## � Pricing

### GPT-Image-1 (Default Model)
| Resolution  | Low    | Medium | High   |
|-------------|--------|--------|--------|
| 512×512     | $0.020 | $0.070 | $0.190 |
| 1024×1024   | $0.040 | $0.140 | $0.380 |
| 2048×2048   | $0.080 | $0.280 | $0.720 |
| 1792×1024   | $0.040 | $0.140 | $0.380 |
| 1024×1792   | $0.040 | $0.140 | $0.380 |

### Other Models
- **DALL-E 3**: $0.040-$0.120 per image
- **DALL-E 2**: $0.016-$0.020 per image
- **Image Analysis**: $0.002 per reference image

## 📊 Logging

The application uses loguru for comprehensive logging:
- **Location**: `logs/` directory
- **Rotation**: Weekly (keeps 4 weeks of logs)
- **Content**: Prompts, responses, costs, errors, and debug info
- **Format**: Timestamped structured logs

## 🐛 Troubleshooting

### Common Issues

1. **"API key not found"**: Ensure `.env` file exists with valid `OPENAI_API_KEY`
2. **"Import errors"**: Run `uv sync` to install dependencies
3. **"Permission denied"**: Check file system permissions for the project directory
4. **"API quota exceeded"**: Check your OpenAI account billing and usage

### Getting Help

If you encounter issues:
1. Check the status messages in the web interface
2. Verify your API key is valid and has credits
3. Ensure all dependencies are installed with `uv sync`

## 📜 License

This project is open source. Please check OpenAI's terms of service for API usage guidelines.