from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class RawDocument(Base):
    __tablename__ = "raw_documents"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
