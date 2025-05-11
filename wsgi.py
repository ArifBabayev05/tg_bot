import time
import sys
import os
from bot import main

def application(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/html')])
    return ["Bot is running!".encode()]

# Run the bot in the background
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Bot crashed: {e}")