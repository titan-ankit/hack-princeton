import os
from pathlib import Path
import re
from datetime import datetime

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from load import Storage, PDF
from db import Base, ChunkMetadata

# --- Database Setup ---
DB_PATH = "vector_metadata.sqlite"
engine = create_engine(f"sqlite:///{DB_PATH}")
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = SessionLocal()

# --- Vector Store Setup ---
FAISS_PATH = "faiss_index"
storage = Storage(path=FAISS_PATH, database=db_session)

# --- Data Directories ---
ACTS_DIR = Path(__file__).parent.parent / "vermont_acts_2026"
JOURNALS_DIR = Path(__file__).parent.parent / "vermont_journals_2026"

# --- Metadata Extraction ---
def get_act_metadata(file_path: Path) -> dict:
    bill_name = file_path.parent.name
    chamber = 'house' if bill_name.startswith('H') else 'senate' if bill_name.startswith('S') else 'joint'
    
    return {
        "file_name": file_path.name,
        "source_url": f"https://legislature.vermont.gov/bill/status/2026/{bill_name}",
        "chamber": chamber,
        "journal_date": None,
        "bill_number": bill_name,
        "act_summary": "summary" in file_path.name.lower(),
        "as_enacted": "enacted" in file_path.name.lower(),
    }

def get_journal_metadata(file_path: Path) -> dict:
    filename = file_path.name
    chamber = 'senate' if filename.lower().startswith('s') else 'house' # Default to house for 'h' and 'j'
    if filename.lower().startswith('j'):
        chamber = 'joint'

    source_url = ""
    if chamber == 'senate':
        source_url = "https://legislature.vermont.gov/senate/service/2026/journal"
    elif chamber == 'house':
        source_url = "https://legislature.vermont.gov/house/service/2026/journal"
    elif chamber == 'joint':
        source_url = "https://legislature.vermont.gov/house/service/2026/joint-assembly"

    date_match = re.search(r'\d{2}(\d{2})(\d{2})', filename)
    journal_date = None
    if date_match:
        month, day = date_match.groups()
        # Assuming the year is 2026 from the folder name context
        year = 2026
        try:
            journal_date = datetime(year, int(month), int(day)).date()
        except ValueError:
            print(f"Warning: Could not parse date from filename {filename}")
            journal_date = None


    return {
        "file_name": filename,
        "source_url": source_url, # This is the page URL, not the PDF URL. Best effort.
        "chamber": chamber,
        "journal_date": journal_date,
        "bill_number": None,
        "act_summary": None,
        "as_enacted": None,
    }

# --- Main Upload Logic ---
def upload_files():
    # Process Acts
    print("Processing acts...")
    if not ACTS_DIR.exists():
        print(f"Warning: Directory not found: {ACTS_DIR}")
    else:
        act_files = list(ACTS_DIR.glob("**/*.pdf"))
        for pdf_path in act_files:
            print(f"Processing {pdf_path}...")
            metadata = get_act_metadata(pdf_path)
            PDF(str(pdf_path), storage, metadata)

    # Process Journals
    print("Processing journals...")
    if not JOURNALS_DIR.exists():
        print(f"Warning: Directory not found: {JOURNALS_DIR}")
    else:
        journal_files = list(JOURNALS_DIR.glob("*.pdf"))
        for pdf_path in journal_files:
            print(f"Processing {pdf_path}...")
            metadata = get_journal_metadata(pdf_path)
            PDF(str(pdf_path), storage, metadata)

    print("Upload complete.")

if __name__ == "__main__":
    upload_files()
