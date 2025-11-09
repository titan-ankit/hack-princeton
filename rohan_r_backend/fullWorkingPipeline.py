"""
Relay Legislative Briefing System - STEP 3: DEDALUS EMAIL PIPELINE
This script uses the agent's NATIVE web search, not the failing MCP.
Chains: Alert Determination -> Article Extraction -> Reading Level -> CTA Text Gen -> Legislator Search -> Email Sending
"""

import asyncio
import json
import smtplib
from email.message import EmailMessage
from typing import Dict, Any, List, Optional
from jinja2 import Template
import re 
import os
import sys
import traceback
from tqdm import tqdm # For progress bars in the terminal

# --- NEW IMPORT ---
# Import the function to load the .env file
from dotenv import load_dotenv

# Ensure these are installed:
# pip install dedalus-labs jinja2 tqdm python-dotenv

from dedalus_labs import AsyncDedalus, DedalusRunner

# --- CONFIGURATION (Loaded from Environment) ---
DEDALUS_API_KEY = os.getenv("DEDALUS_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# --- FILE CONFIG ---
TRANSCRIPT_FILE = 'temporary_transcript.json'
USER_FILE = 'users.json'

# --- READING STYLE MAP ---
READING_STYLE_MAP = {
    "1": {
        "label": "Simple: Action-Focused",
        "instruction": "Simple, Grade 6-8, high readability, active voice, minimal jargon.",
        "example": "New Law Creates Tax Credit.\nVermont passed a new law to help homeowners save money on property taxes."
    },
    "2": {
        "label": "Intermediate: Balanced & Contextual",
        "instruction": "Intermediate, Grade 10-12, balanced sentence structure, standard policy vocabulary.",
        "example": "Property Tax System Adjusted.\nThe legislature has passed a new bill to adjust the state's property tax system."
    },
    "3": {
        "label": "Technical: Precise & Legislative",
        "instruction": "Technical, professional/policy level, retain exact bill numbers, use legal terms.",
        "example": "Amendments to 32 V.S.A. § 6066a.\nThe General Assembly has enacted legislation that amends education property taxes."
    }
}

# --- SYSTEM PROMPTS ---

ALERT_DETERMINATION_PROMPT = """
You are an Alert Determination Agent for 'Relay', a legislative tracking app.
You are a high-speed filter to determine if a transcript is significantly relevant to a user.
You will receive a <user_profile> and a <full_transcript>.
Rules:
1. HIGH PRIORITY ("yes"): Transcript contains substantive discussion of any 'specific_keywords'.
2. LOW PRIORITY ("no"): Transcript only matches 'broad_category' but no specific keywords.
3. EXCEPTION ("yes"): A broad category match becomes "yes" if the discussion is a major new bill OR highly specific to user's location.
4. IRRELEVANT ("no"): Transcript matches nothing.

You must respond ONLY with a JSON object:
{
  "is_alert_worthy": "yes" or "no",
  "matched_keyword": "the keyword that matched or null",
  "reasoning": "brief one-sentence explanation"
}
Output only the JSON, nothing else.
"""

ARTICLE_EXTRACTION_PROMPT = """
You are an AI legislative journalist for 'Relay'.
Read the <full_transcript> and <user_profile>, determine which one broad category is most relevant, and write a concise, neutral article based only on facts in the transcript.
You must respond ONLY with a JSON object:
{
  "is_relevant": true or false,
  "matched_category": "the one broad category or null",
  "headline": "short neutral headline or null",
  "summary": "1-2 sentence summary or null",
  "key_points": ["bullet 1", "bullet 2", "bullet 3"] or []
}
If not relevant, set is_relevant to false and all other fields to null/empty.
Output only the JSON, nothing else.
"""

def create_reading_level_prompt(style_instruction: str, style_example: str) -> str:
    """Creates dynamic system prompt for reading level agent."""
    return f"""
You are an expert copy editor. Rewrite the provided JSON object's text fields to match the user's reading level.
Preserve all facts, names, and key data points. Do not change JSON structure.
<STYLE_DESCRIPTION>
{style_instruction}
</STYLE_DESCRIPTION>
<EXAMPLE_OF_STYLE>
{style_example}
</EXAMPLE_OF_STYLE>
Rewrite 'headline', 'summary', and 'key_points' to match this style.
You must respond ONLY with a JSON object with the same structure as input but rewritten text.
Output only the JSON, nothing else.
"""

CTA_PROMPT = """
You are a non-partisan civic engagement assistant.
Your job is to generate a short, compelling *question* for the user, based on a legislative summary,
urging them to contact their legislator. Make it specific to the topic discussed.

Example:
<article_summary>
The committee discussed H.123, which would cap the Statewide Adjustment (CLA) in the property tax formula...
</article_summary>

Output:
{
  "cta_text": "How will H.123 affect your property taxes? Contact your legislator to share your perspective on the homestead tax formula changes."
}

You must respond ONLY with a JSON object:
{
  "cta_text": "The compelling question and call to action."
}
Output only the JSON, nothing else.
"""

# [--- MODIFIED ---]
# This prompt now explicitly tells the agent to use its BUILT-IN search.
LEGISLATOR_SEARCH_PROMPT = """
You are an expert Vermont legislative researcher.
Your goal is to find the *local representative* for a specific user.
Analyze the user's <COUNTY> and <CITY> provided.
Use your **built-in web search tool** to find the name and official Vermont legislative email address for *one* of the State Representatives (House) or Senators for that user's specific district (e.g., search 'Vermont state representative for Burlington' or 'Vermont state senator for Chittenden County').

You must respond ONLY with a JSON object:
{
  "legislator_name": "Name of the legislator (e.g., 'Rep. Tiff Bluemle')",
  "legislator_email": "The official legislative email (e.g., 'tbluemle@leg.state.vt.us')"
}
If you cannot find a specific person or their email, return null for both fields.
Output only the JSON, nothing else.
"""

# --- HTML EMAIL TEMPLATE ---
BRIEFING_TEMPLATE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Georgia, 'Times New Roman', serif; 
            line-height: 1.7; 
            background-color: #f5f5f5;
            margin: 0;
            padding: 0;
        }
        .container { 
            width: 90%; 
            max-width: 650px; 
            margin: 30px auto; 
            background-color: #ffffff;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .header { 
            background-color: #2b2b2b; 
            padding: 30px 40px; 
            border-bottom: 3px solid #1a1a1a;
        }
        .header h1 { 
            margin: 0; 
            color: #ffffff; 
            font-size: 28px; 
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .subheader {
            color: #b0b0b0;
            font-size: 12px;
            margin-top: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .content { 
            padding: 40px;
            background-color: #ffffff;
        }
        .content p { 
            margin-bottom: 20px; 
            color: #2b2b2b;
            font-size: 16px;
        }
        .priority-badge {
            display: inline-block;
            background-color: #e8e8e8;
            color: #1a1a1a;
            padding: 6px 14px;
            border-radius: 3px;
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 20px;
        }
        .alert-title { 
            font-size: 22px; 
            font-weight: 700; 
            color: #1a1a1a; 
            margin-bottom: 15px;
            line-height: 1.4;
            border-left: 4px solid #2b2b2b;
            padding-left: 20px;
        }
        .meta-info { 
            font-size: 14px; 
            color: #666666; 
            margin-bottom: 25px; 
            padding-bottom: 20px;
            border-bottom: 1px solid #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .summary-box { 
            background-color: #fafafa; 
            border-left: 3px solid #2b2b2b;
            padding: 25px 30px; 
            margin-bottom: 30px;
        }
        .summary-box > p {
            color: #2b2b2b;
            font-size: 16px;
            line-height: 1.7;
        }
        .key-points { 
            margin-top: 25px;
        }
        .key-points b {
            color: #1a1a1a;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: block;
            margin-bottom: 12px;
        }
        .key-points ul { 
            margin: 0 0 15px 20px; 
            padding: 0; 
        }
        .key-points li { 
            margin-bottom: 12px; 
            color: #3a3a3a;
            font-size: 15px;
        }
        .transcript-link {
            display: inline-block;
            color: #2b2b2b;
            font-size: 14px;
            text-decoration: none;
            border-bottom: 2px solid #2b2b2b;
            padding-bottom: 2px;
            margin-top: 10px;
            font-weight: 600;
        }
        .cta-box { 
            background-color: #2b2b2b;
            border: none;
            padding: 35px 30px; 
            text-align: center;
            margin-top: 30px;
        }
        .cta-box p { 
            font-weight: 600; 
            color: #ffffff; 
            margin-bottom: 20px;
            font-size: 17px;
            line-height: 1.5;
        }
        .cta-button { 
            background-color: #ffffff; 
            color: #1a1a1a; 
            padding: 14px 35px; 
            text-decoration: none; 
            font-weight: 700; 
            display: inline-block;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-size: 13px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .footer { 
            background-color: #f5f5f5; 
            padding: 25px 40px; 
            text-align: center; 
            font-size: 12px; 
            color: #666666;
            border-top: 1px solid #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Relay Briefing</h1>
            <div class="subheader">Legislative Monitoring Service</div>
        </div>
        <div class="content">
            <p>Hi {{ user_name }},</p>
            <p>A new legislative proceeding matched your priority:</p>
            <div class="priority-badge">{{ matched_category }}</div>
            
            <div class="summary-box">
                <div class="alert-title">{{ headline }}</div>
                <div class="meta-info">
                    <b>Date:</b> {{ date }} | <b>Source:</b> {{ committee }}
                </div>
                <p>{{ summary }}</p>
                <div class="key-points">
                    <b>Key Points:</b>
                    <ul>
                        {% for point in key_points %}
                            <li>{{ point }}</li>
                        {% endfor %}
                    </ul>
                </div>
                <a href="{{ url }}" class="transcript-link">View Full Transcript →</a>
            </div>

            <div class="cta-box">
                <p>{{ cta_text }}</p>
                {% if legislator_email and legislator_name %}
                    <a href="mailto:{{ legislator_email }}" class="cta-button">Email Your Rep: {{ legislator_name }}</a>
                {% else %}
                    <a href="https://legislature.vermont.gov/people/search" class="cta-button">Find Your Legislator</a>
                {% endif %}
            </div>
            </div>
        <div class="footer">
            <p>You are receiving this briefing as part of your Relay preferences.</p>
        </div>
    </div>
</body>
</html>
"""

# --- LOCAL TOOL: EMAIL SENDING ---

def send_email_tool(to_address: str, subject: str, html_body: str) -> Dict[str, Any]:
    """
    Local Python tool to send email via Gmail SMTP.
    """
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_address
        msg.set_content("Please enable HTML to view this briefing.")
        msg.add_alternative(html_body, subtype='html')
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        return {"success": True, "message": f"Email sent to {to_address}"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- ASYNC JSON PARSING HELPER ---
async def parse_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """Tries to parse JSON, with robust regex fallback."""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                return None
        return None

def print_debug_json(step_name: str, data: Any):
    """Utility to print a formatted JSON blob for debugging."""
    print(f"\n    --- DEBUG: {step_name} ---")
    if data:
        print(f"    {json.dumps(data, indent=2)}")
    else:
        print("    !!! FAILED (Returned None or Empty) !!!")
    print("    ---------------------------------")


# --- DEDALUS AGENT FUNCTIONS ---

async def run_alert_determination(runner: DedalusRunner, user_profile: Dict[str, Any], transcript: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Runs Agent 1: Alert Determination"""
    alert_input = f"""
    <SYSTEM_INSTRUCTION>
    {ALERT_DETERMINATION_PROMPT}
    </SYSTEM_INSTRUCTION>
    <user_profile>
    {json.dumps(user_profile, indent=2)}
    </user_profile>
    <full_transcript>
    {transcript['transcript']}
    </full_transcript>
    Analyze if this transcript warrants a briefing for the user.
    """
    alert_response = await runner.run(
        input=alert_input,
        model="claude-sonnet-4-5"
    )
    return await parse_json_from_response(alert_response.final_output)

async def run_article_extraction(runner: DedalusRunner, user_profile: Dict[str, Any], transcript: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Runs Agent 2: Article Extraction (Summarization)"""
    extraction_input = f"""
    <SYSTEM_INSTRUCTION>
    {ARTICLE_EXTRACTION_PROMPT}
    </SYSTEM_INSTRUCTION>
    <user_profile>
    {json.dumps(user_profile, indent=2)}
    </user_profile>
    <full_transcript>
    {transcript['transcript']}
    </full_transcript>
    Extract a structured article from this transcript.
    """
    extraction_response = await runner.run(
        input=extraction_input,
        model="claude-sonnet-4-5"
    )
    return await parse_json_from_response(extraction_response.final_output)

async def run_reading_level_rewrite(runner: DedalusRunner, article: Dict[str, Any], user_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Runs Agent 3: Reading Level Rewrite"""
    style_choice = user_profile.get('reading_level_choice', '2')
    style_data = READING_STYLE_MAP.get(style_choice, READING_STYLE_MAP['2'])
    reading_prompt = create_reading_level_prompt(style_data['instruction'], style_data['example'])
    
    reading_input = f"""
    <SYSTEM_INSTRUCTION>
    {reading_prompt}
    </SYSTEM_INSTRUCTION>
    <article_json_to_rewrite>
    {json.dumps(article, indent=2)}
    </article_json_to_rewrite>
    Rewrite the headline, summary, and key_points to match the style.
    """
    
    reading_response = await runner.run(
        input=reading_input,
        model="claude-sonnet-4-5"
    )
    
    rewritten_article = await parse_json_from_response(reading_response.final_output)
    if rewritten_article:
        return rewritten_article
    return article  # Fallback to original if parse fails

async def run_cta_generation(runner: DedalusRunner, summary: str) -> Dict[str, str]:
    """Runs Agent 4a: Generates the specific CTA question/text."""
    cta_input = f"""
    <SYSTEM_INSTRUCTION>
    {CTA_PROMPT}
    </SYSTEM_INSTRUCTION>
    <article_summary>
    {summary}
    </article_summary>
    Generate the compelling CTA text.
    """
    
    cta_response = await runner.run(
        input=cta_input,
        model="claude-sonnet-4-5"
    )
    
    cta_data = await parse_json_from_response(cta_response.final_output)
    if not cta_data or not cta_data.get('cta_text'):
        return {"cta_text": "This bill directly impacts your interests. Share your feedback with your local representative."}
        
    return cta_data

# [--- MODIFIED AGENT 4b ---]
async def run_legislator_search_agent(runner: DedalusRunner, user_profile: Dict[str, Any]) -> Dict[str, str]:
    """Runs Agent 4b: Legislator Web Search using the model's NATIVE search."""
    
    search_context = f"""
    <SYSTEM_INSTRUCTION>
    {LEGISLATOR_SEARCH_PROMPT}
    </SYSTEM_INSTRUCTION>

    <COUNTY>
    {user_profile.get('county', 'Vermont')}
    </COUNTY>

    <CITY>
    {user_profile.get('city', 'Vermont')}
    </CITY>

    Find the name and email for one state legislator representing this user's district.
    """
    
    print("      Running Web Search Agent (Native)...")
    search_response = await runner.run(
        input=search_context,
        model="openai/gpt-4o", # Use a powerful model for tool use
        # mcp_servers=["tsion/brave-search-mcp"] # <-- REMOVED. This was the fix.
    )
    
    legislator_data = await parse_json_from_response(search_response.final_output)
    
    if not legislator_data or not legislator_data.get('legislator_email'):
        print("      - Web Search Agent could not find a specific email. Using default.")
        return {
            "legislator_name": None,
            "legislator_email": None
        }
    
    print(f"      ✓ Web Search found: {legislator_data.get('legislator_name')}")
    return legislator_data


# --- MAIN ORCHESTRATION FUNCTION ---

async def main_pipeline():
    """
    Main orchestration function to run the entire pipeline.
    """
    print("="*70)
    print("STEP 3: RELAY LEGISLATIVE BRIEFING PIPELINE (with Native Web Search)")
    print("="*70)
    
    # --- 1. Check for Credentials ---
    if not all([DEDALUS_API_KEY, SENDER_EMAIL, GMAIL_APP_PASSWORD]):
        print("❌ ERROR: Missing one or more environment variables.", file=sys.stderr)
        print("Please ensure DEDALUS_API_KEY, SENDER_EMAIL, and GMAIL_APP_PASSWORD are set in your .env file or system environment.", file=sys.stderr)
        sys.exit(1)
    else:
        print("✓ Environment variables loaded successfully.")

    # --- 2. Load Input Files ---
    print(f"Loading users from '{USER_FILE}'...")
    if not os.path.exists(USER_FILE):
        print(f"❌ ERROR: '{USER_FILE}' not found.", file=sys.stderr)
        sys.exit(1)
    with open(USER_FILE, 'r') as f:
        users = json.load(f)

    print(f"Loading new transcripts from '{TRANSCRIPT_FILE}'...")
    if not os.path.exists(TRANSCRIPT_FILE):
        print(f"❌ ERROR: '{TRANSCRIPT_FILE}' not found. Run Step 2 first.", file=sys.stderr)
        sys.exit(1)
    try:
        with open(TRANSCRIPT_FILE, 'r') as f:
            transcripts_by_chamber = json.load(f)
    except json.JSONDecodeError:
         print(f"❌ ERROR: '{TRANSCRIPT_FILE}' is empty or contains invalid JSON. Did Step 2 fail?", file=sys.stderr)
         sys.exit(1)

    all_new_transcripts = []
    for chamber, committees in transcripts_by_chamber.items():
        for committee, meetings in committees.items():
            all_new_transcripts.extend(meetings)
            
    if not all_new_transcripts:
        print("\n✅ No new transcripts found in 'temporary_transcript.json'. Pipeline complete.")
        sys.exit(0)
        
    print(f"✓ Loaded {len(users)} users and {len(all_new_transcripts)} new transcripts to process.")

    client = AsyncDedalus(api_key=DEDALUS_API_KEY)
    runner = DedalusRunner(client)
    total_emails_sent = 0

    print("\n" + "="*70)
    print(f"STARTING EFFICIENT PIPELINE ({len(all_new_transcripts)} transcripts x {len(users)} users)")
    print("="*70)
    
    for transcript in tqdm(all_new_transcripts, desc="Processing Transcripts", unit="transcript"):
        print(f"\nProcessing Transcript: {transcript['committee_original']} ({transcript['date']})")
        
        print("  Running Article Extraction (Summarization)...")
        article = await run_article_extraction(runner, {}, transcript)
        print_debug_json("Agent 2 (Article Extraction)", article) # <-- DEBUG
        if not article:
            print(f"  ❌ Failed to extract article for {transcript['url']}. Skipping.")
            continue
            
        for user in users:
            print(f"  Checking for User: {user['name']} <{user['email']}>")
            
            alert_result = await run_alert_determination(runner, user, transcript)
            print_debug_json(f"Agent 1 (Alert Check: {user['name']})", alert_result) # <-- DEBUG
            
            if not alert_result:
                print(f"    ❌ Alert Agent failed for user {user['name']}. Skipping.")
                continue

            if alert_result.get('is_alert_worthy') != 'yes':
                print(f"    - Not relevant. Skipping user.")
                continue
                
            print(f"    ✓ RELEVANT: Matched '{alert_result.get('matched_keyword')}'")
            print(f"    Running email generation pipeline...")

            # --- Agent 3: Reading Level Rewrite ---
            rewritten_article = await run_reading_level_rewrite(runner, article, user)
            print_debug_json(f"Agent 3 (Rewrite: {user['name']})", rewritten_article) # <-- DEBUG
            
            # --- Agent 4a: CTA Text Generation ---
            cta_data = await run_cta_generation(runner, rewritten_article.get('summary', ''))
            print_debug_json("Agent 4a (CTA Text)", cta_data) # <-- DEBUG
            
            # --- Agent 4b: Legislator Search [MODIFIED] ---
            legislator_data = await run_legislator_search_agent(runner, user)
            print_debug_json(f"Agent 4b (Legislator Search: {user['name']})", legislator_data) # <-- DEBUG
            
            # --- Step 5: Render HTML ---
            template = Template(BRIEFING_TEMPLATE_HTML)
            email_data = {
                "user_name": user['name'],
                "matched_category": rewritten_article.get('matched_category', 'General Update'),
                "headline": rewritten_article.get('headline', 'Legislative Update'),
                "date": transcript['date'],
                "committee": transcript['committee_original'],
                "summary": rewritten_article.get('summary', 'A relevant update was found.'),
                "key_points": rewritten_article.get('key_points', []),
                "url": transcript['url'],
                "cta_text": cta_data.get("cta_text"), # From Agent 4a
                "legislator_name": legislator_data.get("legislator_name"),     # From Agent 4b
                "legislator_email": legislator_data.get("legislator_email")   # From Agent 4b
            }
            html_output = template.render(email_data)
            
            # --- Step 6: Send Email (Local Tool) ---
            print(f"    Sending email to {user['email']}...")
            email_result = send_email_tool(
                to_address=user['email'],
                subject=f"Relay Briefing: {rewritten_article.get('headline', 'Legislative Update')}",
                html_body=html_output
            )
            
            if email_result.get('success'):
                print(f"    ✓ Email sent successfully.")
                total_emails_sent += 1
            else:
                print(f"    ❌ Email failed: {email_result.get('error')}", file=sys.stderr)

    print("\n" + "="*70)
    print("PIPELINE COMPLETE")
    print("="*70)
    print(f"Total transcripts processed: {len(all_new_transcripts)}")
    print(f"Total users checked: {len(users)}")
    print(f"Total personalized emails sent: {total_emails_sent}")
    print("="*70)


if __name__ == "__main__":
    # Load the .env file *before* running any code
    print("Loading environment variables from .env file...")
    load_dotenv()
    
    # Now that .env is loaded, re-populate the global variables
    DEDALUS_API_KEY = os.getenv("DEDALUS_API_KEY")
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

    try:
        asyncio.run(main_pipeline())
    except Exception as e:
        print(f"\nFATAL ERROR: An unexpected failure occurred: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
