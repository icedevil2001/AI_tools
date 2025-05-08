# Installation Instructions

## Setup Virtual Environment
```bash
# Navigate to the project directory
cd /Users/pri/git/AI_tools/transcriber

# Create a virtual environment if not already created
python -m venv .venv

# Activate the virtual environment
source .venv/bin/activate  # On macOS/Linux
# OR
.venv\Scripts\activate     # On Windows
```

## Install Dependencies
```bash
# Make sure pip is updated
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt

# If moviepy still doesn't work, try installing it directly
pip install moviepy

# Install ffmpeg (required by moviepy and pydub)
# On macOS with Homebrew
brew install ffmpeg

# On Ubuntu/Debian
# sudo apt-get install ffmpeg

# On Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

## Set up API Key
1. Get a Google Gemini API key from https://makersuite.google.com/app/apikey
2. Update the `.env` file with your API key:
   ```
   GOOGLE_API_KEY=your_actual_api_key_here
   ```

## Run the Application
```bash
# Make sure your virtual environment is activated
flask run
```

## Supported File Formats
The application supports the following audio and video formats:
- MP3 (.mp3)
- M4A (.m4a)
- WAV (.wav)
- MP4 (.mp4) - video format with audio extraction

## Troubleshooting

If you see the error "No module named 'moviepy.editor'":

1. Ensure you've activated the virtual environment
2. Try reinstalling with pip:
   ```
   pip uninstall moviepy
   pip install moviepy
   ```
3. Check if ffmpeg is installed on your system

If you have issues with pydub or audio processing:
```
pip install pydub
```

For any dependency with audio processing, ffmpeg is required:
- macOS: `brew install ffmpeg`
- Ubuntu: `sudo apt-get install ffmpeg`
- Windows: Download from ffmpeg.org and add to PATH
