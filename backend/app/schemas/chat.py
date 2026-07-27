from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class DocumentCreate(BaseModel):
    filename: str
    file_type: str
    file_size: int
    knowledge_base_id: int


class DocumentInfo(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    knowledge_base_id: int
    uploaded_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_public: bool = True


class KnowledgeBaseInfo(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    owner_id: int
    is_public: bool
    document_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    title: str = "新对话"
    knowledge_base_ids: Optional[List[int]] = None


class SessionInfo(BaseModel):
    id: int
    title: str
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    role: str
    content: str
    references: Optional[str] = None


class MessageInfo(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    references: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    session_id: int
    message: str


class ChatResponse(BaseModel):
    answer: str
    references: Optional[List[dict]] = None
    session_id: int
    message_id: int
