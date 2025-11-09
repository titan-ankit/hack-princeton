"""
Relay Legislative Briefing System - INCREMENTAL LINK UPDATER
This script loads 'all_committee_links (1).json', scrapes the website for new links,
and saves two files:
1. 'all_committee_links (1).json': The fully updated database (old + new links).
2. 'temporary_committee_links.json': A file containing ONLY the new links found.
"""

import os
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from typing import Dict, List, Tuple
import traceback

# ==== CONFIG ====
BASE_URL = "https://www.goldendomevt.com"
MAIN_PAGE_URL = "https://www.goldendomevt.com"
YEAR = 2025
LINKS_DATABASE_FILE = 'all_committee_links.json' # Use the user-provided file
NEW_LINKS_FILE = 'temporary_committee_links.json'
# ===============

def load_existing_links(filename: str) -> Dict[str, list]:
    """Loads the existing link database from a JSON file."""
    if not os.path.exists(filename):
        print(f"No existing database found at '{filename}'. Will create a new one.")
        return {}
    
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            print(f"✓ Successfully loaded {len(data)} committees from '{filename}'.")
            return data
    except json.JSONDecodeError:
        print(f"⚠️  Error reading '{filename}'. File might be corrupt. Starting fresh.")
        return {}
    except Exception as e:
        print(f"⚠️  An unexpected error occurred loading '{filename}': {e}")
        return {}

def save_links_to_json(filename: str, data: Dict[str, list], purpose: str):
    """Saves the given data to a JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Successfully saved {purpose} to '{filename}'.")
    except Exception as e:
        print(f"❌ FAILED to save {purpose} to '{filename}': {e}")

def update_committee_links(existing_links: Dict[str, list]) -> Tuple[Dict[str, list], Dict[str, list], int]:
    """
    Scrapes the website and incrementally updates the existing_links dict.
    
    Returns three items:
    1. updated_data (old + new links)
    2. new_links_only_data (only new links)
    3. total_new_links_found (count)
    """
    print("Setting up browser...")
    
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in background
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    driver = None
    
    # This will be our main database (old + new)
    updated_data = existing_links.copy()
    # This will store ONLY the new links
    new_links_only_data = {}
    total_new_links_found = 0
    
    try:
        print("Opening browser...")
        driver = webdriver.Chrome(options=chrome_options)
        
        print(f"Loading page: {MAIN_PAGE_URL}")
        driver.get(MAIN_PAGE_URL)
        
        print("Waiting for page to load...")
        time.sleep(5)  # Give JavaScript time to run
        
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "span"))
            )
            print("✓ Page loaded\n")
        except:
            print("⚠️  Timeout waiting for content, but continuing...\n")
        
        all_spans = driver.find_elements(By.TAG_NAME, "span")
        
        chamber_spans = []
        for span in all_spans:
            try:
                span_text = span.text.strip()
                if span_text in ['Senate', 'House']:
                    chamber_spans.append((span_text, span))
            except:
                pass
        
        print(f"✓ Found {len(chamber_spans)} chambers. Starting scrape...\n")
        
        for chamber_name, chamber_span in chamber_spans:
            print(f"📂 {chamber_name.upper()}")
            print("-" * 70)
            
            chamber_parent_li = driver.execute_script("return arguments[0].closest('li');", chamber_span)
            if not chamber_parent_li: continue
            
            chamber_nested_uls = chamber_parent_li.find_elements(By.CSS_SELECTOR, "ul.nested")
            if not chamber_nested_uls: continue
            
            chamber_ul = chamber_nested_uls[0]
            committee_lis = chamber_ul.find_elements(By.CSS_SELECTOR, "li.folder")
            
            for committee_li in committee_lis:
                try:
                    committee_spans = committee_li.find_elements(By.TAG_NAME, "span")
                    if not committee_spans: continue
                    
                    committee_name = committee_spans[0].text.strip()
                    if not committee_name or committee_name.isdigit(): continue
                    
                    full_committee_name = f"{chamber_name} - {committee_name}"
                    print(f"  Checking: {committee_name}...")
                    
                    # --- MODIFIED LOGIC START ---
                    
                    # Initialize this committee in the "new links" dict with an empty list
                    new_links_only_data[full_committee_name] = []
                    
                    # Get the set of links we already have for fast lookup
                    known_links_set = set(updated_data.get(full_committee_name, []))
                    new_links_for_this_committee = []
                    found_overlap = False
                    
                    committee_nested_uls = committee_li.find_elements(By.CSS_SELECTOR, "ul.nested")
                    if not committee_nested_uls:
                        print("    - No meetings found.")
                        continue
                    
                    committee_ul = committee_nested_uls[0]
                    transcript_items = committee_ul.find_elements(By.CSS_SELECTOR, "li.transcript-link-item")
                    
                    if not transcript_items:
                        print("    - No meetings found.")
                        continue

                    # Iterate through links on the website (newest to oldest)
                    for item in transcript_items:
                        try:
                            link = item.find_element(By.TAG_NAME, "a")
                            href = link.get_attribute('href')
                            
                            if not href:
                                continue

                            # Core incremental logic:
                            if href in known_links_set:
                                # We found a link we already have. Stop checking.
                                found_overlap = True
                                break
                            else:
                                # This is a new link.
                                new_links_for_this_committee.append(href)
                        
                        except Exception as e:
                            print(f"    ⚠️ Error parsing a link item: {e}")

                    # After checking all links, update both data dictionaries
                    if new_links_for_this_committee:
                        print(f"    + Found {len(new_links_for_this_committee)} new link(s).")
                        total_new_links_found += len(new_links_for_this_committee)
                        
                        # 1. Add to the "new links only" dictionary
                        new_links_only_data[full_committee_name] = new_links_for_this_committee
                        
                        # 2. Add to the main cumulative dictionary
                        existing_links_list = updated_data.get(full_committee_name, [])
                        updated_data[full_committee_name] = new_links_for_this_committee + existing_links_list
                    
                    else:
                        print("    - Already up-to-date.")
                    
                    # --- MODIFIED LOGIC END ---

                except Exception as e:
                    print(f"  ❌ Error processing committee: {e}")
                    pass
            print("-" * 70)
        
        return updated_data, new_links_only_data, total_new_links_found
        
    except Exception as e:
        print(f"❌ A fatal error occurred during scraping: {e}")
        traceback.print_exc()
        # Return the old data and empty new links to avoid data loss
        return existing_links, {}, 0
    
    finally:
        if driver:
            print("\nClosing browser...")
            driver.quit()

# --- MAIN EXECUTION BLOCK ---

if __name__ == "__main__":
    print("="*70)
    print("VERMONT LEGISLATURE MEETING LINK UPDATER")
    print(f"Main Database: {LINKS_DATABASE_FILE}")
    print(f"New Links File: {NEW_LINKS_FILE}")
    print("="*70 + "\n")

    # 1. Load existing links
    known_links = load_existing_links(LINKS_DATABASE_FILE)
    if not known_links:
        print("\nStarting fresh. Will perform a full scrape...")
    else:
        total_known_links = sum(len(links) for links in known_links.values())
        print(f"Loaded {total_known_links} existing links across {len(known_links)} committees.\n")

    print("="*70)
    print("Starting incremental scrape...")
    print("="*70 + "\n")

    # 2. Run the update process
    # This now returns THREE values
    updated_links_data, new_links_data, new_links_count = update_committee_links(known_links)
    
    print("\n" + "="*70)
    print("SCRAPE COMPLETE")
    print("="*70 + "\n")

    # 3. Save results
    if new_links_count > 0:
        print(f"✅ Success! Found {new_links_count} new meeting link(s).")
        # 1. Save the cumulative (old + new) database
        save_links_to_json(LINKS_DATABASE_FILE, updated_links_data, "full updated database")
        # 2. Save the "new links only" temporary file
        save_links_to_json(NEW_LINKS_FILE, new_links_data, "new links temporary file")
        
    elif not updated_links_data:
        print("❌ No data was scraped. Check for website or script errors.")
    else:
        print("✅ System is already 100% up-to-date. No new links found.")
        # We still save the "new links" file, which will contain all committees with empty lists
        save_links_to_json(NEW_LINKS_FILE, new_links_data, "empty new links file")

    print("\n" + "="*70)
