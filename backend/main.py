from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import warnings

from load import Storage, Retrieval
from db import SessionLocal, init_db

# Suppress the specific UserWarning from FAISS
warnings.filterwarnings("ignore", message="FAISS index file not found at faiss_index")

# Initialize DB and get a session
init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize Storage. We should load it from path.
FAISS_PATH = "faiss_index"

app = FastAPI()

# Dependency to get the storage object
# This will create a new Storage object for each request that depends on it.
# It will load the FAISS index from disk each time.
# For a production scenario, you might want to load this once at startup.
def get_storage(db: Session = Depends(get_db)):
    return Storage(path=FAISS_PATH, database=db, from_path=True)


class QueryRequest(BaseModel):
    question: str

class DocumentResponse(BaseModel):
    content: str
    metadata: dict

class QueryResponse(BaseModel):
    question: str
    response: str
    documents: list[DocumentResponse]


@app.post("/query", response_model=QueryResponse)
def query_rag(request: QueryRequest, storage: Storage = Depends(get_storage)):
    """
    Accepts a question and returns a RAG-based answer.
    """
    if not storage.vector_store:
        return {"error": "Vector store not found. Please run the upload script first."}
        
    result: Retrieval = storage.rag(request.question)
    
    # The result contains Document objects, which are not directly JSON serializable.
    # We format it into our response model.
    return {
        "question": result["question"],
        "response": result["response"],
        "documents": [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            } for doc in result["documents"]
        ]
    }

@app.get("/")
def read_root():
    return {"message": "RAG API is running. POST to /query with a question."}
