from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from sqlalchemy.orm import Session
from app.schemas.domain import IngestionResponse
from app.db.session import get_db
from app.services.db_service import db_service
from app.services.llm_service import llm_service
import fitz # PyMuPDF
import re
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

def simple_text_splitter(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    A lightweight, no-dependency text chunker using paragraphs and sentences.
    """
    # Split by standard paragraphs first
    paragraphs = re.split(r'\n{2,}', text)
    
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        # Rough estimation: 1 word ~ 1 token (simplification)
        para_words = paragraph.split()
        
        # If adding this paragraph exceeds chunk size, save current chunk and start new
        if len(current_chunk.split()) + len(para_words) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            
            # Start new chunk with overlap from the END of the previous chunk
            words = current_chunk.split()
            overlap_words = " ".join(words[-overlap:]) if len(words) > overlap else current_chunk
            current_chunk = overlap_words + "\n\n" + paragraph
        else:
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
                
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

@router.post("/pdf", response_model=IngestionResponse)
async def ingest_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    content = await file.read()
    
    # Extract text using PyMuPDF locally
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")

    # Tokenizer Check (simple whitespace heuristic)
    words = full_text.split()
    token_count = len(words)
    
    # 1. Always save to PostgreSQL
    db_service.save_raw_text(db, full_text, file.filename, token_count)
    logger.info(f"Saved {file.filename} to PostgreSQL with {token_count} estimated tokens.")
    
    # 2. Always embed into Qdrant (Fix: small files were previously skipping Qdrant, breaking RAG)
    chunks = simple_text_splitter(full_text, chunk_size=500, overlap=50)
    logger.info(f"Split {file.filename} into {len(chunks)} chunks for vector embedding.")
    
    vectors = []
    for c in chunks:
        vec = await llm_service.embed_question(c)
        vectors.append(vec)
         
    await db_service.store_chunk_vectors(chunks, vectors, file.filename)
    logger.info(f"Successfully stored {len(vectors)} chunk vectors in Qdrant for {file.filename}.")
    
    return IngestionResponse(status="success", token_count=token_count, storage="postgres+qdrant")

@router.get("/files")
async def get_files(db: Session = Depends(get_db)):
    docs = db_service.get_all_documents(db)
    return {"files": [{"id": d.id, "source_name": d.source_name} for d in docs]}
