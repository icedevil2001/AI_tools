import hashlib
import os
import uuid
from functools import wraps
from flask import session, redirect, url_for, flash, request, g
from pymongo import MongoClient
import datetime

# Initialize MongoDB connection with environment variables for flexibility
MONGO_HOST = os.environ.get('MONGO_HOST', 'localhost')
MONGO_PORT = os.environ.get('MONGO_PORT', '27017')
MONGO_USER = os.environ.get('MONGO_USER', 'transcriber')
MONGO_PASSWORD = os.environ.get('MONGO_PASSWORD', 'transcriber_password')
MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/"

print(f"Connecting to MongoDB at: {MONGO_HOST}:{MONGO_PORT}")

try:
    client = MongoClient(MONGO_URI)
    # Try to access the server info to test the connection
    server_info = client.server_info()
    print(f"Successfully connected to MongoDB version: {server_info.get('version', 'unknown')}")
    db = client.transcriber_db
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    # Fallback to try localhost
    if MONGO_HOST != 'localhost':
        print("Trying to connect to localhost...")
        try:
            MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@localhost:{MONGO_PORT}/"
            client = MongoClient(MONGO_URI)
            db = client.transcriber_db
            print("Successfully connected to MongoDB on localhost")
        except Exception as e2:
            print(f"Error connecting to MongoDB on localhost: {e2}")
            raise e  # Raise the original error if fallback also fails

users_collection = db.users
transcripts_collection = db.transcripts

def init_db(app):
    """Initialize the database and ensure indexes"""
    # Add indexes to improve query performance
    users_collection.create_index('email', unique=True)
    users_collection.create_index('username', unique=True)
    
    # Store MongoDB connection in app config
    app.config['MONGO_CLIENT'] = client
    app.config['MONGO_DB'] = db

def hash_password(password, salt=None):
    """Hash a password with salt using SHA-256"""
    if not salt:
        salt = os.urandom(32)  # Generate a new salt if not provided
    
    # Combine password and salt then hash
    hash_obj = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt, 
        100000  # Number of iterations
    )
    
    return hash_obj, salt

def register_user(username, email, password):
    """Register a new user"""
    # Check if username or email already exists
    if users_collection.find_one({'$or': [{'username': username}, {'email': email}]}):
        return False, "Username or email already exists"
    
    # Hash password with salt
    password_hash, salt = hash_password(password)
    
    # Create user document
    user = {
        'username': username,
        'email': email,
        'password_hash': password_hash,
        'salt': salt,
        'created_at': datetime.datetime.utcnow(),
        'user_id': str(uuid.uuid4()),
        'sessions': []
    }
    
    # Insert into database
    users_collection.insert_one(user)
    return True, "User registered successfully"

def authenticate_user(email, password):
    """Authenticate a user with email and password"""
    user = users_collection.find_one({'email': email})
    
    if not user:
        return None, "Invalid email or password"
    
    # Verify password
    stored_hash = user['password_hash']
    salt = user['salt']
    
    # Debug log to inspect types
    print(f"Authenticating user: {email}")
    print(f"Type of stored hash: {type(stored_hash)}")
    print(f"Type of salt: {type(salt)}")
    
    # If the stored hash is a string (hex representation), convert it to bytes
    if isinstance(stored_hash, str):
        try:
            stored_hash = bytes.fromhex(stored_hash)
        except ValueError:
            print("Could not convert stored hash from hex to bytes")
    
    # If the salt is a string (hex representation), convert it to bytes
    if isinstance(salt, str):
        try:
            salt = bytes.fromhex(salt)
        except ValueError:
            print("Could not convert salt from hex to bytes")
    
    verify_hash, _ = hash_password(password, salt)
    
    # Debug log to compare hashes
    print(f"Generated hash: {verify_hash.hex()}")
    print(f"Stored hash: {stored_hash.hex() if isinstance(stored_hash, bytes) else stored_hash}")
    
    # Compare the hashes properly
    if isinstance(stored_hash, bytes) and verify_hash == stored_hash:
        # Return user info for session
        return {
            'user_id': user['user_id'],
            'username': user['username'],
            'email': user['email']
        }, "Login successful"
    
    return None, "Invalid email or password"

def login_required(f):
    """Decorator to require login for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page", "warning")
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def get_user_transcripts(user_id):
    """Get all transcripts for a user"""
    try:
        # Add explicit sorting by created_at in descending order (newest first)
        return list(transcripts_collection.find(
            {'user_id': user_id}
        ).sort("created_at", -1))
    except Exception as e:
        print(f"Error retrieving transcripts: {e}")
        # Return empty list on error instead of failing
        return []
    

def save_user_transcript(user_id, transcript_data):
    if transcript_data.get('transcript'):
        first_line = transcript_data['transcript'].split('\n')[0][:40]
        if first_line:
            # Remove speaker labels if present
            default_title = first_line.split(': ', 1)[-1] if ':' in first_line else first_line

    # Create the transcript document
    transcript = {
        'user_id': user_id,
        'transcript': transcript_data.get('transcript', ''),
        'audioUrl': transcript_data.get('audioUrl', ''),
        'summary': transcript_data.get('summary', ''),
        'created_at': datetime.datetime.utcnow(),
        'transcript_id': transcript_data.get('transcript_id', str(uuid.uuid4())),
        'title': transcript_data.get('title', default_title)
    }

    # Check if this transcript already exists
    existing = transcripts_collection.find_one({
        'user_id': user_id,
        'transcript_id': transcript['transcript_id']
    })

    if existing:
        # Update existing transcript but preserve created_at to maintain sort order
        if existing.get('created_at'):
            transcript['created_at'] = existing['created_at']
        result = transcripts_collection.update_one(
            {'_id': existing['_id']},
            {'$set': transcript}
        )
        return str(existing['_id'])
    else:
        # Insert new transcript
        result = transcripts_collection.insert_one(transcript)
        return str(result.inserted_id)


def update_transcript_summary(user_id, transcript_id, summary):
    """Update the summary for an existing transcript"""
    result = transcripts_collection.update_one(
        {
            'user_id': user_id,
            'transcript_id': transcript_id
        },
        {
            '$set': {
                'summary': summary
            }
        }
    )
    return result.modified_count > 0


def update_transcript_title(user_id, transcript_id, title):
    """Update the title of a transcript"""
    transcripts = transcripts_collection.find_one({
        'user_id': user_id,
        'transcript_id': transcript_id
    })
    if not transcripts:
        print(f"Transcript with ID {transcript_id} not found for user {user_id}")
        return False
    if transcripts.get('title') == title:
        print(f"Transcript title is already set to {title}")
        return True

    result = transcripts_collection.update_one(
        {
            'user_id': user_id,
            'transcript_id': transcript_id
        },
        {
            '$set': {
                'title': title
            }
        }
    )

    print(f"Updated transcript title for {transcript_id} to {title}")
    print(f"Result: {result.modified_count}")
    print(f"Result: {result}")
    return result.modified_count > 0


def delete_transcript(user_id, transcript_id):
    """Delete a transcript"""
    result = transcripts_collection.delete_one({
        'user_id': user_id,
        'transcript_id': transcript_id
    })
    return result.deleted_count > 0


def get_transcript(transcript_id, user_id=None):
    """Get a specific transcript by ID, optionally checking user ownership"""
    query = {'transcript_id': transcript_id}
    if user_id:
        query['user_id'] = user_id  # Add user check if user_id provided

    return transcripts_collection.find_one(query)
