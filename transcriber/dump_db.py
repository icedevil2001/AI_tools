#!/usr/bin/env python
"""
Database dump utility for Transcriber app
Dumps MongoDB user database and transcripts to JSON files
"""

import os
import json
import datetime
import hashlib
from pymongo import MongoClient
from bson import json_util
import argparse
import sys
from pathlib import Path
import logging
from pprint import pprint 
import click

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dump_db')

# MongoDB connection settings
MONGO_URI = 'mongodb://transcriber:transcriber_password@localhost:27017/'
DB_NAME = 'transcriber_db'

# Output directory
DEFAULT_OUTPUT_DIR = 'db_backup'


class EnhancedJSONEncoder(json.JSONEncoder):
    """Enhanced JSON encoder that handles MongoDB dates and binary data"""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            # Convert binary data (like password salt) to hex string
            return obj.hex()
        try:
            # Use json_util for BSON objects
            return json_util.default(obj)
        except TypeError:
            return str(obj)  # Fallback to string


def anonymize_user_data(user_data, anonymize=True):
    """Anonymize sensitive user data for safe export"""
    if not anonymize:
        return user_data
    
    # Create a copy to avoid modifying the original
    result = user_data.copy()
    
    # Anonymize email
    if 'email' in result:
        parts = result['email'].split('@')
        if len(parts) == 2:
            domain = parts[1]
            username = hashlib.md5(parts[0].encode()).hexdigest()[:8]
            result['email'] = f"{username}@{domain}"
    
    # Anonymize username
    if 'username' in result:
        result['username'] = hashlib.md5(result['username'].encode()).hexdigest()[:8]
    
    # Remove password hash and salt
    if 'password_hash' in result:
        result['password_hash'] = '[REDACTED]'
    
    if 'salt' in result:
        result['salt'] = '[REDACTED]'
    
    return result


def dump_db_to_json(output_dir=DEFAULT_OUTPUT_DIR, anonymize=True):
    """Dump database collections to JSON files"""
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Dump users collection
        users = list(db.users.find())
        if anonymize:
            users = [anonymize_user_data(user) for user in users]
        
        with open(os.path.join(output_dir, 'users.json'), 'w') as f:
            json.dump(users, f, cls=EnhancedJSONEncoder, indent=2)
        
        logger.info(f"Exported {len(users)} users to {output_dir}/users.json")
        
        # Dump transcripts collection
        transcripts = list(db.transcripts.find())
        with open(os.path.join(output_dir, 'transcripts.json'), 'w') as f:
            json.dump(transcripts, f, cls=EnhancedJSONEncoder, indent=2)
        
        logger.info(f"Exported {len(transcripts)} transcripts to {output_dir}/transcripts.json")
        
        # Create a summary file with statistics
        summary = {
            'dump_date': datetime.datetime.now().isoformat(),
            'user_count': len(users),
            'transcript_count': len(transcripts),
            'anonymized': anonymize
        }
        
        with open(os.path.join(output_dir, 'summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)
        
        dump_api_usage_collection()

        logger.info(f"Database dump completed successfully to {output_dir}/")
        return True
    

        
    except Exception as e:
        logger.error(f"Error dumping database: {str(e)}")
        return False


def list_users(limit=10, anonymize=True):
    """List users in the database (useful for quick inspection)"""
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        # Get users, limiting to specified count
        users = list(db.users.find().limit(limit))
        
        if anonymize:
            users = [anonymize_user_data(user) for user in users]
        
        # Print user information
        print(f"\nUser listing (showing {len(users)} of {db.users.count_documents({})} users):")
        print("-" * 80)
        
        for i, user in enumerate(users, 1):
            print(f"{i}. Username: {user.get('username')}")
            print(f"   User ID: {user.get('user_id')}")
            print(f"   Email: {user.get('email')}")
            print(f"   Created: {user.get('created_at')}")
            
            # Get transcript count for this user
            transcript_count = db.transcripts.count_documents({"user_id": user.get('user_id')})
            print(f"   Transcripts: {transcript_count}")
            print("-" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return False

def dump_by_user(user_id, output_dir, limit:int=None):
    """ Dump the transcript by user_id"""
    # try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    # Get users, limiting to specified count
    user = db.users.find_one({"username": user_id})

    user = anonymize_user_data(user)
    pprint(user)

    transcripts = list(db.transcripts.find({"user_id": user.get('user_id')}).limit(limit))
    # logger.info(f'   Found Transcripts {len(transcripts)}')
    with open(os.path.join(output_dir, f'{user.get("user_id")}.transcripts.json'), 'w') as f:
        json.dump(transcripts, f, cls=EnhancedJSONEncoder, indent=2)


    # logger.info(f"Database dump completed successfully to {output_dir}/")
    logger.info(f"Exported {len(transcripts)} transcripts to {output_dir}/{user.get('user_id')}.transcripts.json")

        
    # except Exception as e:
    #     logger.error(f"Error list users data {user_id}")
    #     return False
    


def dump_api_usage_collection():
    """Dump API usage collection to JSON file"""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    api_calls = list(db.api_calls.find())
    with open(os.path.join(DEFAULT_OUTPUT_DIR, 'api_calls.json'), 'w') as f:
        json.dump(api_calls, f, cls=EnhancedJSONEncoder, indent=2)
    logger.info(f"Exported {len(api_calls)} API calls to {DEFAULT_OUTPUT_DIR}/api_calls.json")
    # logger.info(f"Database dump completed successfully to {output_dir}/")

@click.command()
@click.option('--output', '-o', default=DEFAULT_OUTPUT_DIR, help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})')
@click.option('--list', '-l', is_flag=True, help='List users instead of dumping the database')
@click.option('--count', '-c', default=10, type=int, help='Number of users to list (default: 10)')
@click.option('--no-anonymize', '-na', is_flag=True, help='Disable anonymization (WARNING: includes sensitive data)')
@click.option('--user-id', '-u', type=str, help='Dump data based on user ID')
def main(output, list, count, no_anonymize, user_id):
    """Database dump utility for Transcriber app"""
    if list:
        if not list_users(limit=count, anonymize=not no_anonymize):
            sys.exit(1)
    elif user_id:
        dump_by_user(user_id=user_id, output_dir=output, limit=count)
    else:
        if not dump_db_to_json(output_dir=output, anonymize=not no_anonymize):
            sys.exit(1)


if __name__ == "__main__":
    main()
