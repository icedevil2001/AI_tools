from flask import Flask, render_template, request, jsonify, send_from_directory, session
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

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_CACHE'] = 'audio_cache'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # Increased to 32MB max-limit

# Configure Gemini API with latest client pattern
api_key = os.environ.get('GOOGLE_API_KEY')
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
                
                # Track token usage and cost
                # Rough estimation of prompt tokens
                prompt_tokens = estimate_tokens(prompt)
                # Rough estimation of response tokens
                response_tokens = estimate_tokens(response.text)
                total_tokens = prompt_tokens + response_tokens
                
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
            
            return "\n".join(full_transcript)
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
            
            # Track token usage and cost
            prompt_tokens = estimate_tokens(prompt)
            response_tokens = estimate_tokens(response.text)
            total_tokens = prompt_tokens + response_tokens
            
            # Get or create session cost tracker
            session_id = request.environ.get('HTTP_X_SESSION_ID')
            if session_id and session_id not in session_costs:
                session_costs[session_id] = CostTracker()
            
            if session_id:
                session_costs[session_id].add_request(
                    "transcription", total_tokens, TRANSCRIPTION_MODEL)
            
            return response.text
    except Exception as e:
        print(f"Transcription error: {str(e)}")
        return f"Error during transcription: {str(e)}"

def generate_summary(transcript):
    """Generate a summary of the transcript using Gemini API."""
    try:
        prompt = f"""
        Please provide a concise summary of the following transcript.
        Focus on the key points, main topics discussed, and any important conclusions.

        Format your response in Markdown style using the following layout:
        
        ## Summary
        A brief summary of the overall conversation.
    
        ## Main Takeaways
        - Key Point 1
        - Key Point 2
        - Key Point 3
        
        ## Action Items
        - Action Item 1
        - Action Item 2
        
        Use bullet points for better readability. Make sure the output is valid Markdown format.

        Transcript:
        {transcript}
        """
        
        # Use the same model that works for transcription
        response = api_call_with_rate_limiting(
            SUMMARY_MODEL,
            client.models.generate_content,
            contents=[{"role": "user", "parts": [{"text": prompt}]}]
        )
        
        # Track token usage and cost
        prompt_tokens = estimate_tokens(prompt)
        response_tokens = estimate_tokens(response.text)
        total_tokens = prompt_tokens + response_tokens
        
        # Get or create session cost tracker
        session_id = request.environ.get('HTTP_X_SESSION_ID')
        if session_id and session_id not in session_costs:
            session_costs[session_id] = CostTracker()
        
        if session_id:
            session_costs[session_id].add_request(
                "text", total_tokens, SUMMARY_MODEL)
        
        return response.text
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
        prompt_tokens = estimate_tokens(prompt)
        response_tokens = estimate_tokens(response.text)
        total_tokens = prompt_tokens + response_tokens
        
        # Get or create session cost tracker
        session_id = request.environ.get('HTTP_X_SESSION_ID')
        if session_id and session_id not in session_costs:
            session_costs[session_id] = CostTracker()
        
        if session_id:
            session_costs[session_id].add_request(
                "text", total_tokens, QnA_MODEL)
        
        return response.text
    except Exception as e:
        print(f"Question answering error: {str(e)}")
        return f"Error processing your question: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

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

@app.route('/transcribe', methods=['POST'])
def transcribe():
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
            
            transcript = transcribe_audio(audio_path)
            os.remove(audio_path)
        else:
            # Copy the file to cache for playback
            shutil.copy2(filepath, cached_path)
            audio_url = f"/audio/{cache_filename}"
            logger.info(f"Audio cached at: {audio_url}")
            
            transcript = transcribe_audio(filepath)

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
            'sessionId': session_id
        })
        
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
    data = request.json
    if not data or 'transcript' not in data:
        logger.warning("No transcript provided for summarization")
        return jsonify({'error': 'No transcript provided'}), 400
    
    transcript = data['transcript']
    logger.info(f"Generating summary for transcript of length: {len(transcript)}")
    summary = generate_summary(transcript)
    logger.info("Summary generated successfully")
    
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
    
    answer = answer_question(transcript, question)
    logger.info("Question answered successfully")
    
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

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(debug=True)
