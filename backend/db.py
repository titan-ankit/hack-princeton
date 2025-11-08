from sqlalchemy import create_engine, Column, String, Date, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class ChunkMetadata(Base):
    __tablename__ = "chunk_metadata"

    id = Column(String, primary_key=True, index=True) # This will be the UUID from FAISS
    file_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    chamber = Column(String) # 'house', 'senate', 'joint'
    journal_date = Column(Date)
    bill_number = Column(String)
    
    # Extra fields as requested
    act_summary = Column(Boolean)
    as_enacted = Column(Boolean)
    extra_metadata1 = Column(Text) # Example of empty field
    extra_metadata2 = Column(Text) # Example of empty field

DATABASE_URL = "sqlite:///./vector_metadata.sqlite"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
