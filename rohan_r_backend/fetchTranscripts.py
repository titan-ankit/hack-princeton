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
