#!/usr/bin/env python
import os
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

CACHE_DIR = 'audio_cache'
UPLOADS_DIR = 'uploads'
MAX_AGE_HOURS = 24

def cleanup_old_files(directory, max_age_hours):
    """Remove files older than max_age_hours from the specified directory."""
    if not os.path.exists(directory):
        logging.warning(f"Directory does not exist: {directory}")
        return 0
    
    count = 0
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            file_age = current_time - os.path.getctime(filepath)
            if file_age > max_age_seconds:
                try:
                    os.remove(filepath)
                    count += 1
                except Exception as e:
                    logging.error(f"Failed to remove {filepath}: {str(e)}")
    
    return count

if __name__ == "__main__":
    logging.info("Starting cleanup process...")
    
    # Clean up audio cache
    count_cache = cleanup_old_files(CACHE_DIR, MAX_AGE_HOURS)
    logging.info(f"Removed {count_cache} old files from {CACHE_DIR}")
    
    # Clean up uploads folder (should be empty, but check just in case)
    count_uploads = cleanup_old_files(UPLOADS_DIR, 1)  # More aggressive cleanup for uploads
    logging.info(f"Removed {count_uploads} old files from {UPLOADS_DIR}")
    
    logging.info("Cleanup complete!")
