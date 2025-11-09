import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import sys

# Ensure tqdm is available for the terminal version
# NOTE: Run 'pip install requests beautifulsoup4 tqdm' before executing this script.

# ==== CONFIG ====
# Input file is the temporary file with only NEW links
INPUT_FILE = 'temporary_committee_links.json'
# --- MODIFIED ---
# Output file will be the new file requested, not an overwrite
OUTPUT_FILE = 'temporary_transcript.json'
# Number of concurrent scrapers. Adjust based on your connection/server limits.
MAX_WORKERS = 20
# ================

# --- Helper Functions ---

def extract_meeting_info_from_url(url):
    """Extract meeting info from URL pattern (Used for fallback metadata)"""
    match = re.search(r'/([^/]+)\.html$', url)
    if match:
        filename_base = match.group(1)
        parts = filename_base.split('_')
        if len(parts) >= 3:
            committee_code = parts[0].replace('VT', '')
            date_str = parts[1] if len(parts) > 1 else ''
            time_str = parts[2] if len(parts) > 2 else ''
            return {'committee': committee_code, 'date': date_str, 'time': time_str.replace('-', ':')}
    return None

def extract_transcript(soup):
    """Extract the full transcript text from the page (Robust Version)"""
    # This robust logic is identical to the provided helper function
    body_text = soup.get_text()
    lines = [line.strip() for line in body_text.split('\n') if line.strip()]
    
    transcript_lines = []
    start_found = False
    
    for line in lines:
        if not start_found:
            if 'SmartTranscript of' in line or re.search(r'\[.*?\]:', line):
                start_found = True
        
        if start_found:
            # Filter out known UI junk
            if (len(line) > 10 and 
                not line.startswith('Select text') and
                not line.startswith('Play Clip') and
                'This transcript was computer-produced' not in line and
                'Like closed-captioning' not in line and
                not line.startswith('SmartTranscript of') and
                'Speaker IDs are still experimental' not in line and
                'function(' not in line and 
                'document.getElementById' not in line):
                
                transcript_lines.append(line)
