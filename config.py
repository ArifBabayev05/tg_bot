import os
from dotenv import load_dotenv

# Get the directory containing this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from .env file
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Bot configuration
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
BOT_USERNAME = os.getenv('BOT_USERNAME')

# Directory configurations
DB_DIR = os.path.join(BASE_DIR, 'db')
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
IMAGES_DIR = os.path.join(BASE_DIR, 'images')

# Create directories if they don't exist
for directory in [DB_DIR, DOWNLOADS_DIR, IMAGES_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)