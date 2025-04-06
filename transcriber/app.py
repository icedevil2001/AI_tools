from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, flash
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import uuid
from google import genai
from google.genai import types
import shutil
import sys
import traceback
import logging
import json
import re
import time
from functools import wraps
import hashlib
from pathlib  import Path 
import user_auth
from pymongo import MongoClient    # (if not already imported)
import datetime

# Try to import required packages with informative errors
try:
    from moviepy.editor import VideoFileClip
except ImportError:
    print("ERROR: MoviePy not installed properly. Please run: pip install moviepy")

try:
    from pydub import AudioSegment
    from pydub.silence import split_on_silence
except ImportError:
    print("ERROR: PyDub not installed. Please run: pip install pydub")

TRANSCRIPTION_MODEL = "gemini-2.0-flash"  # Updated model name
QnA_MODEL = "gemini-2.0-flash"  # Updated model name
SUMMARY_MODEL = "gemini-2.0-flash"  # Updated model name


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('transcriber')

dotenv_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_CACHE'] = 'audio_cache'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # Increased to 32MB max-limit

# Initialize session config with more secure settings
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours in seconds
app.config['SESSION_TYPE'] = 'filesystem'
# Disable secure cookie for local development (enable in production with HTTPS)
app.config['SESSION_COOKIE_SECURE'] = False  # Changed from True to False for local development
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize the database
user_auth.init_db(app)

# Configure Gemini API with latest client pattern
api_key = os.environ.get('GOOGLE_API_KEY')
print(api_key)
if not api_key:
    logger.error("NO API KEY FOUND! Make sure GOOGLE_API_KEY is set in your .env file")
else:
    logger.info(f"Using API Key: {api_key[-8:-4]}****")
    
try:
    client = genai.Client(api_key=api_key)
    # Test the API connectivity
    models = client.models.list()
    logger.info(f"Successfully connected to Gemini API - Available models: {[m.name for m in models]}")
except Exception as e:
    logger.error(f"Failed to initialize Gemini API: {e}")
    traceback.print_exc()

# Supported audio formats
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'm4a', 'wav'}

# Ensure upload and cache folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AUDIO_CACHE'], exist_ok=True)

# API cost settings
API_COSTS = {
    "transcription": 0.00001,  # $0.00001 per token for audio transcription
    "text": 0.000005,  # $0.000005 per token for text generation
}

class CostTracker:
    def __init__(self):
        self.total_tokens = 0
        self.total_cost = 0
        self.request_breakdown = []
        
    def add_request(self, request_type, tokens, model_name):
        """Add a request to the cost tracker"""
        cost_per_token = API_COSTS.get(request_type, 0.000005)
        cost = tokens * cost_per_token
        
        self.total_tokens += tokens
        self.total_cost += cost
        
        self.request_breakdown.append({
            "request_type": request_type,
            "model": model_name,
            "tokens": tokens,
            "cost": cost
        })
        
        return cost
    
    def get_summary(self):
        """Get a summary of costs"""
        return {
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "requests": self.request_breakdown
        }

# Track costs by session
session_costs = {}


def get_token_from_response(response):
    """Extract token usage from the response"""

    if hasattr(response, 'usage_metadata'):
        result =  {
            "total_token_count": response.usage_metadata.total_token_count, 
            "prompt_tokens": response.usage_metadata.prompt_token_count, 
            "response_tokens": response.usage_metadata.candidates_token_count, 
            # "model_version": getattr(response.candidates, 'model_version', 'unknown') if hasattr(response, 'candidates') else 'unknown'
            }
        logger.info(f"Token usage: {result}")
        return result
    elif hasattr(response, 'metadata'):
        return response.metadata.total_token_count
    else:
        raise ValueError("Response does not contain token usage metadata")

# Estimate tokens in text
def estimate_tokens(text):
    """Roughly estimate the number of tokens in a text."""
    if not text:
        return 0
    # A simple estimation: ~4 characters per token on average
    return len(text) // 4

def get_mime_type(file_extension):
    """Return the correct MIME type based on file extension."""
    mime_types = {
        'mp3': 'audio/mpeg',
        'm4a': 'audio/m4a',
        'wav': 'audio/wav',
    }
    return mime_types.get(file_extension.lower(), 'audio/wav')

def segment_audio(audio_path):
    """Split audio into segments based on silence."""
    # Convert to WAV for processing if not already WAV
    file_ext = os.path.splitext(audio_path)[1][1:].lower()
    
    if file_ext != 'wav':
        print(f"Converting {file_ext} to WAV for processing")
        try:
            audio = AudioSegment.from_file(audio_path, format=file_ext)
            temp_wav_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_processing.wav')
            audio.export(temp_wav_path, format="wav")
            audio_path = temp_wav_path
        except Exception as e:
            print(f"Error converting to WAV: {str(e)}")
            return [audio_path]  # Return original if conversion fails
    else:
        audio = AudioSegment.from_file(audio_path)
    
    # Get audio duration in seconds
    duration_seconds = len(audio) / 1000
    
    # For shorter audio files (less than 5 minutes), don't segment
    if duration_seconds < 300:
        logger.info(f"Audio file is short ({duration_seconds:.1f}s), processing as a single segment")
        return [audio_path]
    
    # Split on silence with adjusted parameters to create fewer segments
    try:
        chunks = split_on_silence(
            audio, 
            # Increase minimum silence length (from 1000ms to 2000ms)
            min_silence_len=3000,  # 2 seconds of silence required
            # Lower threshold (more negative = stricter silence detection)
            silence_thresh=-45,     # -45 dBFS (was -40)
            # Keep more silence to maintain context
            keep_silence=500        # 500ms of silence at the start/end (was 300)
        )
        
        # If we still have too many segments, combine segments to limit their number
        max_segments = 10  # Maximum desired segments
        
        if len(chunks) > max_segments:
            logger.info(f"Too many segments ({len(chunks)}), combining to {max_segments} segments")
            # Calculate how many original segments to combine into each new segment
            segments_per_group = len(chunks) // max_segments + 1
            combined_chunks = []
            
            for i in range(0, len(chunks), segments_per_group):
                # Combine a group of segments
                group = chunks[i:i + segments_per_group]
                if group:
                    combined = group[0]
                    for chunk in group[1:]:
                        combined += chunk
                    combined_chunks.append(combined)
            
            chunks = combined_chunks
    except Exception as e:
        print(f"Error splitting audio: {str(e)}")
        return [audio_path]
    
    logger.info(f"Audio split into {len(chunks)} segments")
    
    # If no segments were found or just one, use the original file
    if not chunks or len(chunks) < 2:
        return [audio_path]
    
    # Save each chunk as a separate audio file
    segment_files = []
    for i, chunk in enumerate(chunks):
        segment_filename = f"segment_{i}_{uuid.uuid4().hex[:6]}.wav"
        segment_path = os.path.join(app.config['UPLOAD_FOLDER'], segment_filename)
        chunk.export(segment_path, format="wav")
        segment_files.append(segment_path)
    
    return segment_files

# API rate limiting settings
RATE_LIMITS = {
    "gemini-2.0-flash": {
        "requests_per_minute": 10,  # Set slightly below the actual limit of 15
        "cooldown_period": 60,      # Seconds to wait when hitting a rate limit
    }
}

class RateLimiter:
    def __init__(self):
        self.last_request_time = {}  # Model -> list of timestamps
        self.in_cooldown = {}        # Model -> cooldown end time
        
    def check_rate_limit(self, model):
        """Check if we're within rate limits for the model."""
        current_time = time.time()
        
        # Check if we're in cooldown
        if model in self.in_cooldown and current_time < self.in_cooldown[model]:
            remaining_wait = int(self.in_cooldown[model] - current_time)
            return False, f"Rate limit cooldown: {remaining_wait}s remaining"
        
        # Initialize timestamp list if needed
        if model not in self.last_request_time:
            self.last_request_time[model] = []
        
        # Remove timestamps older than 60 seconds
        self.last_request_time[model] = [
            t for t in self.last_request_time[model] 
            if current_time - t < 60
        ]
        
        # Check if we've hit the rate limit
        model_limits = RATE_LIMITS.get(model, {"requests_per_minute": 10})
        if len(self.last_request_time[model]) >= model_limits["requests_per_minute"]:
            # Enter cooldown mode
            cooldown_seconds = model_limits.get("cooldown_period", 60)
            self.in_cooldown[model] = current_time + cooldown_seconds
            return False, f"Rate limit reached: cooling down for {cooldown_seconds}s"
        
        return True, ""
    
    def record_request(self, model):
        """Record a request for the model."""
        if model not in self.last_request_time:
            self.last_request_time[model] = []
        self.last_request_time[model].append(time.time())
    
    def get_status(self, model):
        """Get current rate limit status."""
        current_time = time.time()
        
        # Check if we're in cooldown
        if model in self.in_cooldown and current_time < self.in_cooldown[model]:
            remaining_wait = int(self.in_cooldown[model] - current_time)
            return {
                "status": "cooldown",
                "remaining_seconds": remaining_wait,
                "requests_available": 0
            }
        
        # Initialize timestamp list if needed
        if model not in self.last_request_time:
            self.last_request_time[model] = []
        
        # Remove timestamps older than 60 seconds
        self.last_request_time[model] = [
            t for t in self.last_request_time[model] 
            if current_time - t < 60
        ]
        
        # Calculate available requests
        model_limits = RATE_LIMITS.get(model, {"requests_per_minute": 10})
        requests_made = len(self.last_request_time[model])
        requests_available = max(0, model_limits["requests_per_minute"] - requests_made)
        
        return {
            "status": "ok",
            "requests_available": requests_available,
            "requests_made": requests_made,
            "limit": model_limits["requests_per_minute"]
        }

# Create a global rate limiter
rate_limiter = RateLimiter()

# Helper function for API calls with rate limiting
def api_call_with_rate_limiting(model_name, func, *args, **kwargs):
    """Execute an API call with rate limiting and retry logic."""
    max_retries = 3
    base_delay = 2  # seconds
    
    for attempt in range(max_retries + 1):
        # Check rate limit before attempting
        can_proceed, message = rate_limiter.check_rate_limit(model_name)
        
        if not can_proceed:
            if attempt < max_retries:
                # Calculate exponential backoff delay
                delay = message.split(':', 1)[1].strip() if ':' in message else "2s"
                if 'cooldown' in message:
                    delay_seconds = int(delay.split('s')[0])
                else:
                    delay_seconds = base_delay * (2 ** attempt)
                
                logger.info(f"Rate limit reached. Waiting {delay_seconds}s before retry {attempt+1}/{max_retries}")
                time.sleep(delay_seconds)
                continue
            else:
                raise Exception(f"Rate limit exceeded: {message}. Max retries reached.")
        
        try:
            # Record this request
            rate_limiter.record_request(model_name)
            
            # Add the model parameter to kwargs if we're calling generate_content
            if func.__name__ == 'generate_content' and 'model' not in kwargs:
                kwargs['model'] = model_name
            
            # Execute the actual API call
            return func(*args, **kwargs)
            
        except Exception as e:
            error_message = str(e)
            
            # Check if this is a rate limit error
            if "429" in error_message and "RESOURCE_EXHAUSTED" in error_message:
                if attempt < max_retries:
                    # Try to extract retry delay from the error
                    retry_delay_match = re.search(r"retryDelay': '(\d+)s'", error_message)
                    if retry_delay_match:
                        delay_seconds = int(retry_delay_match.group(1))
                    else:
                        delay_seconds = base_delay * (2 ** attempt)
                    
                    logger.info(f"Rate limit hit (429). Waiting {delay_seconds}s before retry {attempt+1}/{max_retries}")
                    
                    # Update the rate limiter's cooldown
                    rate_limiter.in_cooldown[model_name] = time.time() + delay_seconds
                    
                    time.sleep(delay_seconds)
                    continue
            
            # For other errors or if we've hit max retries, re-raise
            logger.error(f"API call error: {error_message}")
            raise

def transcribe_audio(audio_path):
    try:
        # Get the file extension for MIME type
        file_ext = os.path.splitext(audio_path)[1][1:].lower()
        mime_type = get_mime_type(file_ext)
        print(f"Transcribing audio with MIME type: {mime_type}")
        
        # First try to segment the audio to identify potential speakers
        segment_files = segment_audio(audio_path)
        
        if len(segment_files) > 1:
            # Process segments for speaker identification
            full_transcript = []
            
            for i, segment_path in enumerate(segment_files):
                with open(segment_path, 'rb') as audio_file:
                    audio_content = audio_file.read()
                
                # Specific prompt for speaker identification
                prompt = """
                    Please transcribe this audio segment accurately. If there are multiple speakers, 
                    identify and label each speaker as Speaker 1, Speaker 2, etc., based on their unique voice characteristics 
                    such as tone, pitch, and speech patterns. If the speaker's name is mentioned or can be inferred, 
                    use their name instead of Speaker X for identification.

                    Format the transcript as:
                    Speaker X: [transcribed text]
                    or
                    [Speaker Name]: [transcribed text]

                    Ensure consistency in speaker labeling across segments. If the same speaker continues from a previous segment, 
                    maintain the same label or name. Clearly differentiate between speakers and provide a clean, readable transcript.
                """
                
                # Since segments are always converted to WAV
                response = api_call_with_rate_limiting(
                    TRANSCRIPTION_MODEL,
                    client.models.generate_content,
                    contents=[
                        {"role": "user", "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_content}}
                        ]}
                    ]
                )
                # print(f">>> {response}")
                # Track token usage and cost
                # Rough estimation of prompt tokens
                # prompt_tokens = estimate_tokens(prompt)
                # # Rough estimation of response tokens
                # response_tokens = estimate_tokens(response.text)
                # total_tokens = prompt_tokens + response_tokens
                token_usage = get_token_from_response(response)
                total_tokens = token_usage["total_token_count"]
                
                # Get or create session cost tracker
                session_id = request.environ.get('HTTP_X_SESSION_ID')
                if session_id and session_id not in session_costs:
                    session_costs[session_id] = CostTracker()
                
                if session_id:
                    session_costs[session_id].add_request(
                        "transcription", total_tokens, TRANSCRIPTION_MODEL)
                
                if response.text.strip():
                    full_transcript.append(response.text)
                
                # Clean up segment file
                os.remove(segment_path)
            
            return {
                "transcript": "\n".join(full_transcript),
                "token_usage": token_usage
                }
        else:
            # Single audio file processing with speaker detection request
            with open(audio_path, 'rb') as audio_file:
                audio_content = audio_file.read()
            
            prompt = """
            Please transcribe this audio file accurately. If there are multiple speakers,
            clearly identify and label each speaker as Speaker 1, Speaker 2, etc.
            Format the transcript as:
            Speaker X: [transcribed text]
            
            Differentiate speakers based on voice characteristics, tone, pitch, and speech patterns.
            """
            
            response = api_call_with_rate_limiting(
                TRANSCRIPTION_MODEL,
                client.models.generate_content,
                contents=[
                    {"role": "user", "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime_type, "data": audio_content}}
                    ]}
                ]
            )
            
            # # Track token usage and cost
            # prompt_tokens = estimate_tokens(prompt)
            # response_tokens = estimate_tokens(response.text)
            # total_tokens = prompt_tokens + response_tokens
            token_usage = get_token_from_response(response)
            total_tokens = token_usage["total_token_count"]
            
            # Get or create session cost tracker
            session_id = request.environ.get('HTTP_X_SESSION_ID')
            if session_id and session_id not in session_costs:
                session_costs[session_id] = CostTracker()
            
            if session_id:
                session_costs[session_id].add_request(
                    "transcription", total_tokens, TRANSCRIPTION_MODEL)
            
            return {
                "transcript": response.text, 
                "token_usage": token_usage
                }
    except Exception as e:
        print(f"Transcription error: {str(e)}")
        return f"Error during transcription: {str(e)}"

def generate_summary(transcript):
    """Generate a summary of the transcript using Gemini API."""
    try:
        prompt = f"""
        Please provide a detailed and comprehensive summary of the following transcript.
        Ensure that all key points, main topics discussed, and important conclusions are covered thoroughly.
        Highlight any significant details, decisions, or insights shared during the conversation.

        Additionally, create a descriptive and engaging title for the summary that captures the essence of the discussion.

        Format your response in Markdown style using the following layout:
        
        # [Title]

        
        ## Summary
        Provide a detailed and structured summary of the entire conversation, covering all key aspects and topics discussed.

        ## Main Takeaways
        - Highlight the most important points or conclusions drawn during the discussion.
        - Ensure each takeaway is clear and concise.

        ## Key Insights
        - Include any unique or noteworthy insights shared during the conversation.
        - Provide context for why these insights are significant.

        ## Action Items
        - List all actionable steps or decisions made during the discussion.
        - Ensure each action item is specific and clearly defined.

        ## Additional Notes
        - Include any other relevant information or observations that may be useful for future reference.

        Use bullet points and headings for better readability. Ensure the output is valid Markdown format.

        Transcript:
        {transcript}
        """
        
        # Use the same model that works for transcription
        response = api_call_with_rate_limiting(
            SUMMARY_MODEL,
            client.models.generate_content,
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        
        # print(f">>> Summary: {response}")
        # print(dir(response))

        # Track token usage and cost
        # prompt_tokens = estimate_tokens(prompt)
        # response_tokens = estimate_tokens(response.text)
        # print(f' usage_metadata: {response.usage_metadata}')
        # prompt_tokens = response.usage_metadata.prompt_token_count
        # print(f' prompt_tokens: {prompt_tokens}')
        # response_tokens = response.usage_metadata.candidates_token_count
        # print(f' response_tokens: {response_tokens}')
        # total_tokens = prompt_tokens + response_tokens
        token_usage = get_token_from_response(response)
        total_tokens = token_usage["total_token_count"]
        
        # Get or create session cost tracker
        session_id = request.environ.get('HTTP_X_SESSION_ID')
        if session_id and session_id not in session_costs:
            session_costs[session_id] = CostTracker()
        
        if session_id:
            session_costs[session_id].add_request(
                "text", total_tokens, SUMMARY_MODEL)
        
        return {'summary': response.text, 
                'token_usage': token_usage
                }
    except Exception as e:
        print(f"Summary generation error: {str(e)}")
        return f"Could not generate summary due to an error: {str(e)}"

def answer_question(transcript, question):
    """Answer questions about the transcript using Gemini API."""
    try:
        prompt = f"""
        You are analyzing a transcript and answering questions about it.
        
        Transcript:
        {transcript}
        
        Question: {question}
        
        Please answer the question based on the information in the transcript only.
        If the transcript doesn't contain the information needed, say so clearly.
        """
        
        # Use the same model that works for transcription
        response = api_call_with_rate_limiting(
            QnA_MODEL,
            client.models.generate_content,
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        
        # Track token usage and cost
        # prompt_tokens = estimate_tokens(prompt)
        # response_tokens = estimate_tokens(response.text)
        # total_tokens = prompt_tokens + response_tokens
        token_usage = get_token_from_response(response)
        total_tokens = token_usage["total_token_count"]
        
        # Get or create session cost tracker
        session_id = request.environ.get('HTTP_X_SESSION_ID')
        if session_id and session_id not in session_costs:
            session_costs[session_id] = CostTracker()
        
        if session_id:
            session_costs[session_id].add_request(
                "text", total_tokens, QnA_MODEL)
        
        return {"response": response.text,
                "token_usage": token_usage
                }

    except Exception as e:
        print(f"Question answering error: {str(e)}")
        return f"Error processing your question: {str(e)}"

@app.route('/')
def index():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('index.html', username=session.get('username'))

@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serve cached audio files for playback."""
    return send_from_directory(app.config['AUDIO_CACHE'], filename)

def generate_cache_filename(file_obj, filename):
    """Generate a unique cache filename based on the file content."""
    # Use MD5 hash of the file content for uniqueness
    hasher = hashlib.md5()
    
    # Check if file_obj is a FileStorage object (from Flask uploads)
    if hasattr(file_obj, 'read') and callable(file_obj.read):
        # Save current position
        current_position = file_obj.tell()
        # Reset to beginning of file
        file_obj.seek(0)
        
        # Read and hash content
        while chunk := file_obj.read(8192):
            hasher.update(chunk)
            
        # Reset file pointer back to original position
        file_obj.seek(current_position)
    else:
        # Handle as regular file path
        with open(file_obj, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
    
    hash_hex = hasher.hexdigest()
    return f"{hash_hex}_{filename}"

# NEW: helper function to record each API call
def record_api_call(user_id, request_type, total_token_count, prompt_tokens, response_tokens, model_version):
    """Record an API call with token usage and cost into a new collection."""
    call_doc = {
        "user_id": user_id,
        "request_type": request_type,
        "total_token_count": total_token_count,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "model_version": model_version,
        "datetime": datetime.datetime.utcnow()
    }
    db = app.config.get("MONGO_DB")
    # FIX: Compare explicitly with None
    if db is not None:
        db.api_calls.insert_one(call_doc)
        logger.debug(f"API call recorded: {call_doc}")
    else:
        # Fallback if using a global client
        client = MongoClient()  # Adjust the connection if necessary
        client.transcriber_db.api_calls.insert_one(call_doc)
        logger.debug(f"Fallback API call recorded: {call_doc}")

@app.route('/transcribe', methods=['POST'])
def transcribe():
    # Add user verification
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
        
    logger.info("Transcribe endpoint called")
    if 'file' not in request.files:
        logger.warning("No file uploaded")
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        logger.warning("No file selected")
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    file_ext = os.path.splitext(filename)[1][1:].lower()
    logger.info(f"Processing file: {filename} (type: {file_ext})")
    
    # Check if file extension is allowed
    if file_ext not in ALLOWED_AUDIO_EXTENSIONS and file_ext != 'mp4':
        logger.warning(f"Unsupported file format: {file_ext}")
        return jsonify({'error': f'Unsupported file format. Allowed formats: mp3, m4a, wav, mp4'}), 400
    
    # Generate unique ID for this upload
    unique_id = uuid.uuid4().hex
    logger.info(f"Generated session ID: {unique_id}")
    
    # Save the original file
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    logger.info(f"File saved to: {filepath}")
    
    # Create a copy for playback
    # Generate a unique cache filename using MD5 hash - now using the file object correctly
    cache_filename = generate_cache_filename(file, filename)
    cached_path = os.path.join(app.config['AUDIO_CACHE'], cache_filename)
    
    # Handle audio differently based on file type
    audio_url = None
    try:
        if filename.lower().endswith('.mp4'):
            logger.info("Processing MP4 file")
            video = VideoFileClip(filepath)
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_audio.wav')
            video.audio.write_audiofile(audio_path)
            logger.info("Extracted audio from video")
            
            # Also save a copy in cache for playback
            audio_cache_filename = f"{unique_id}_audio.wav"
            audio_cache_path = os.path.join(app.config['AUDIO_CACHE'], audio_cache_filename)
            shutil.copy2(audio_path, audio_cache_path)
            audio_url = f"/audio/{audio_cache_filename}"
            logger.info(f"Audio cached at: {audio_url}")
            
            response = transcribe_audio(audio_path)
            transcript = response['transcript']
            usage_metadata = response['token_usage']
            os.remove(audio_path)
        else:
            # Copy the file to cache for playback
            shutil.copy2(filepath, cached_path)
            audio_url = f"/audio/{cache_filename}"
            logger.info(f"Audio cached at: {audio_url}")
            
            response = transcribe_audio(filepath)
            transcript = response['transcript']
            usage_metadata = response['token_usage']
        logger.info("Transcription completed successfully")
        
        # Clean up original upload
        os.remove(filepath)
        
        # Generate a unique session ID for this transcript
        session_id = str(uuid.uuid4())
        
        # Create a cost tracker for this session
        session_costs[session_id] = CostTracker()
        
        # Store transcript in session for later use in Q&A
        session[f'transcript_{session_id}'] = transcript
        logger.info(f"Transcript stored in session with ID: {session_id}")
        
        # Set session ID in response header for the client to track
        response = jsonify({
            'transcript': transcript,
            'audioUrl': audio_url,
            'sessionId': session_id,
            'user_id': session.get('user_id')  # Add user ID
        })
        
        # When saving transcript data, also save to user's collection
        if 'user_id' in session:
            transcript_data = {
                'transcript': transcript,
                'audioUrl': audio_url,
                'summary': '',  # Initialize with empty summary
                'transcript_id': session_id,  # Use the same session_id as transcript_id for consistency
                "api_cost": session_costs[session_id].total_cost,
                "total_token_count": session_costs[session_id].total_tokens,
                "prompt_tokens": 0,  # Placeholder, update with actual prompt tokens
                "response_tokens": 0,  # Placeholder, update with actual response tokens
                "model_version": TRANSCRIPTION_MODEL
            }
            transcript_data.update(usage_metadata)
            user_auth.save_user_transcript(session['user_id'], transcript_data)
            # Record API call details in new collection (for tracking over all users)
            # record_api_call(session['user_id'], "transcription", session_costs[session_id].total_tokens, 0, 0, TRANSCRIPTION_MODEL)
            record_api_call(session['user_id'], "transcription",
                usage_metadata['total_token_count'],
                usage_metadata['prompt_tokens'],
                usage_metadata['response_tokens'],
                TRANSCRIPTION_MODEL
            )
        return response
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        traceback.print_exc()
        # Clean up on error
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500

# Add a cleanup route to periodically remove old cached files
@app.route('/cleanup', methods=['POST'])
def cleanup_cache():
    """Admin route to clean up old cached audio files."""
    try:
        # Get all files in the cache directory
        files = os.listdir(app.config['AUDIO_CACHE'])
        count = len(files)
        
        # Remove all files
        for file in files:
            file_path = os.path.join(app.config['AUDIO_CACHE'], file)
            if os.path.isfile(file_path):
                os.unlink(file_path)
                
        return jsonify({'message': f'Successfully cleaned up {count} files'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/summarize', methods=['POST'])
def summarize():
    """Generate a summary of the transcript."""
    logger.info("Summarize endpoint called")
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    data = request.json
    if not data or 'transcript' not in data:
        logger.warning("No transcript provided for summarization")
        return jsonify({'error': 'No transcript provided'}), 400
    
    transcript = data['transcript']
    logger.info(f"Generating summary for transcript of length: {len(transcript)}")
    response = generate_summary(transcript)
    summary = response['summary']
    usage_metadata = response['token_usage']
    logger.info(f"Summary generated with token usage: {usage_metadata}")
    title = summary.split('\n')[0].replace('# ', '') if summary else "No title generated"
    logger.info(f"Generated summary title: {title}")
    logger.info("Summary generated successfully")
    
    record_api_call(session['user_id'], "summarization",
                usage_metadata['total_token_count'],
                usage_metadata['prompt_tokens'],
                usage_metadata['response_tokens'],
                SUMMARY_MODEL
            )
    # Check if user is logged in and session ID is provided
    if 'user_id' in session and 'sessionId' in data:
        session_id = data['sessionId']
        user_id = session.get('user_id')
        
        try:
            # Update the transcript document with the summary
            result = user_auth.transcripts_collection.update_one(
                {
                    'user_id': user_id,
                    'transcript_id': session_id,
                    "title": title
                },
                {
                    '$set': {
                        'summary': summary,
                        'title': title
                        }
                }
            )
            
            if result.matched_count > 0:
                logger.info(f"Summary saved to database for session ID: {session_id}")
            else:
                # Try to find by the transcript content if session_id doesn't match transcript_id
                result = user_auth.transcripts_collection.update_one(
                    {
                        'user_id': user_id,
                        'transcript': transcript,

                    },
                    {
                        '$set': {
                            'summary': summary,
                            'title': title,
                            }
                    }
                )
                if result.matched_count > 0:
                    logger.info("Summary saved to database (matched by transcript content)")
                else:
                    logger.warning("Could not find matching transcript to update with summary")

            # res = user_auth.update_transcript_title(
            #     user_id=user_id,
            #     transcript_id=session_id,
            #     title=title
            # )
            # if res:
            #     logger.info(f"Transcript title updated in database for session ID: {session_id}")
            # else:
            #     logger.warning(f"Failed to update transcript title in database for session ID: {session_id}")
        except Exception as e:
            logger.error(f"Error saving summary to database: {str(e)}")
    
    return jsonify({'summary': summary})

@app.route('/ask_question', methods=['POST'])
def ask_question():
    """Answer a question about the transcript."""
    logger.info("Ask question endpoint called")
    data = request.json
    if not data:
        logger.warning("No data provided to ask_question endpoint")
        return jsonify({'error': 'No data provided'}), 400
    
    if 'question' not in data:
        logger.warning("No question provided")
        return jsonify({'error': 'No question provided'}), 400
        
    if 'sessionId' not in data:
        logger.warning("No session ID provided")
        return jsonify({'error': 'No session ID provided'}), 400
    
    session_id = data['sessionId']
    question = data['question']
    logger.info(f"Processing question: '{question}' for session: {session_id}")
    
    # Get the stored transcript for this session
    transcript = session.get(f'transcript_{session_id}')
    if not transcript:
        logger.warning(f"No transcript found for session ID: {session_id}")
        # Fallback to transcript provided in the request
        transcript = data.get('transcript', '')
        if not transcript:
            logger.error("No transcript found in session or request")
            return jsonify({'error': 'Transcript not found'}), 404
        else:
            logger.info("Using transcript provided in request as fallback")
    
    response = answer_question(transcript, question)
    answer = response['response']
    usage_metadata = response['token_usage']
    logger.info(f"Answer generated with token usage: {usage_metadata}")

    logger.info("Question answered successfully")

    record_api_call(session['user_id'], "QandA",
                usage_metadata['total_token_count'],
                usage_metadata['prompt_tokens'],
                usage_metadata['response_tokens'],
                QnA_MODEL
            )
    return jsonify({'answer': answer})

# For debugging - add a route to check session content
@app.route('/debug/session', methods=['GET'])
def debug_session():
    """Debug route to display session content."""
    logger.info("Debug session endpoint called")
    session_data = {}
    for key in session:
        if key.startswith('transcript_'):
            session_id = key.split('_')[1]
            transcript = session[key]
            session_data[session_id] = {
                'transcript_length': len(transcript),
                'transcript_preview': transcript[:100] + '...' if len(transcript) > 100 else transcript
            }
    return jsonify(session_data)

# Add a route to get the current session's cost
@app.route('/cost/<session_id>', methods=['GET'])
def get_session_cost(session_id):
    """Get the cost information for a session."""
    if session_id not in session_costs:
        return jsonify({'error': 'Session not found'}), 404
    
    cost_summary = session_costs[session_id].get_summary()
    print(cost_summary)
    return jsonify(cost_summary)

# Add a route to get rate limit status
@app.route('/rate_limits', methods=['GET'])
def get_rate_limits():
    """Get current rate limit status for all models."""
    models = [TRANSCRIPTION_MODEL, SUMMARY_MODEL, QnA_MODEL]
    status = {}
    
    for model in models:
        status[model] = rate_limiter.get_status(model)
    
    return jsonify(status)

# Add authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    # Check if already logged in
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Add debugging output for auth process
        print(f"Attempting login for: {email}")
        
        if not email or not password:
            flash("Please enter both email and password", "danger")
            return render_template('login.html')
        
        user, message = user_auth.authenticate_user(email, password)
        
        if user:
            # Store user info in session
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['email'] = user['email']
            session.permanent = True  # Use permanent session
            
            print(f"Login successful for {email}, user_id: {user['user_id']}")
            print(f"Session data: {dict(session)}")
            
            flash("Login successful!", "success")
            
            # Redirect to the next page or index
            next_page = request.args.get('next', url_for('index'))
            return redirect(next_page)
        else:
            flash(message, "danger")
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User signup page"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Basic validation
        if not username or not email or not password:
            flash("Please fill in all required fields", "danger")
            return render_template('signup.html')
        
        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template('signup.html')
        
        if len(password) < 8:
            flash("Password must be at least 8 characters long", "danger")
            return render_template('signup.html')
        
        # Register user
        success, message = user_auth.register_user(username, email, password)
        
        if success:
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for('login'))
        else:
            flash(message, "danger")
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    """Log user out"""
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for('login'))

@app.route('/profile')
@user_auth.login_required
def profile():
    """User profile page"""
    user_id = session.get('user_id')
    user_transcripts = user_auth.get_user_transcripts(user_id)
    
    return render_template('profile.html', 
                           username=session.get('username'),
                           email=session.get('email'),
                           transcripts=user_transcripts)

# Add a debug route to view session data
@app.route('/debug/user_session')
def debug_user_session():
    """Debug route to see what's in the user session"""
    if 'user_id' in session:
        return jsonify({
            'logged_in': True,
            'user_id': session.get('user_id'),
            'username': session.get('username'),
            'email': session.get('email')
        })
    else:
        return jsonify({
            'logged_in': False,
            'session_data': dict(session)
        })

# Add new API routes for transcript management
@app.route('/api/transcripts', methods=['GET'])
@user_auth.login_required
def get_user_transcripts_api():
    """API endpoint to get all user transcripts"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    transcripts = user_auth.get_user_transcripts(user_id)
    
    # Convert MongoDB documents to JSON-serializable format
    result = []
    for t in transcripts:
        result.append({
            'transcript_id': t.get('transcript_id', ''),
            'title': t.get('title', ''),
            'created_at': t.get('created_at').isoformat() if t.get('created_at') else None,
            'has_summary': bool(t.get('summary')),
            'preview': t.get('transcript', '')[:100] + '...' if len(t.get('transcript', '')) > 100 else t.get('transcript', '')
        })
    
    return jsonify({'transcripts': result})

@app.route('/api/transcript/<transcript_id>', methods=['GET'])
@user_auth.login_required
def get_transcript_by_id(transcript_id):
    """API endpoint to get a specific transcript"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    transcript = user_auth.get_transcript(transcript_id, user_id)
    
    if not transcript:
        return jsonify({'error': 'Transcript not found'}), 404
    
    # Return the transcript data
    return jsonify({
        'transcript_id': transcript.get('transcript_id', ''),
        'title': transcript.get('title', ''),
        'transcript': transcript.get('transcript', ''),
        'summary': transcript.get('summary', ''),
        'audioUrl': transcript.get('audioUrl', ''),
        'created_at': transcript.get('created_at').isoformat() if transcript.get('created_at') else None,
        'sessionId': transcript.get('transcript_id', '')  # Use transcript_id as session_id for consistency
    })

@app.route('/api/transcript/<transcript_id>/title', methods=['PUT'])
@user_auth.login_required
def update_transcript_title(transcript_id):
    """API endpoint to update a transcript title"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Get the new title from request
    data = request.json
    if not data or 'title' not in data:
        return jsonify({'error': 'No title provided'}), 400
    
    new_title = data['title']
    
    # Update the title in database
    result: bool = user_auth.update_transcript_title(user_id, transcript_id, new_title)
    
    if result:
        return jsonify({'success': True, 'title': new_title})
    else:
        return jsonify({'error': 'Failed to update title'}), 500

@app.route('/api/transcript/<transcript_id>', methods=['DELETE'])
@user_auth.login_required
def delete_transcript(transcript_id):
    """API endpoint to delete a transcript"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Delete the transcript
    result = user_auth.delete_transcript(user_id, transcript_id)
    
    if result:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to delete transcript'}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(host='0.0.0.0', port=5000, debug=True)
