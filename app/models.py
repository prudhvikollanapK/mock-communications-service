from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, func
from app.database import Base

class CallRecord(Base):
    __tablename__ = "calls"

    call_id = Column(String(36), primary_key=True, index=True)
    api_key_hash = Column(String(64), nullable=False, index=True)
    caller = Column(String(100), nullable=False)
    callee = Column(String(100), nullable=False)
    state = Column(String(20), nullable=False, index=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    recording_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                         onupdate=func.now(), nullable=False)

class ApiKeyConfig(Base):
    __tablename__ = "api_key_configs"

    api_key_hash = Column(String(64), primary_key=True)
    concurrent_limit = Column(Integer, nullable=False, default=3)
    cps_limit = Column(Integer, nullable=False, default=2)
