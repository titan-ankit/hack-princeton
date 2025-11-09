import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
import json
from langchain_core.messages import SystemMessage, HumanMessage

from schemas import UserQueryRequest, UserQueryResponse
from chat_query import create_agent_graph
from load import Storage

load_dotenv()

app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:3000", # Default for Next.js
    "http://localhost:8080", # I see this in your old logs
    # Add your frontend's actual origin if it's different
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # List of origins that are allowed to make requests
    allow_credentials=True,      # Allow cookies/authorization headers
    allow_methods=["*"],         # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],         # Allow all headers
)

# --- App Initialization ---
FAISS_PATH = "../faiss_index"
storage = Storage(path=FAISS_PATH, from_path=True)
app_graph = create_agent_graph(storage)

with open('prompts.json') as f:
    prompts = json.load(f)
system_prompt = prompts['user_query']

# --- API Endpoint ---
@app.post("/user-query", response_model=UserQueryResponse)
async def user_query_endpoint(user_request: UserQueryRequest):
    """
    Handles user queries.
    """
    
    inputs = {"messages": [SystemMessage(content=system_prompt), HumanMessage(content=user_request.user_query)]}
    response = app_graph.invoke(inputs)
    
    return response['final_response']