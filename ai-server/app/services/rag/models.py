from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any

class IngestRequest(BaseModel):
    table: str
    id_col: Optional[str] = None
    title_col: Optional[str] = None
    text_cols: Optional[List[str]] = None
    save_name: Optional[str] = None
    simulate: bool = True

class IngestResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ok: bool
    save_dir: str
    rows: int
    chunks: int
    schema_info: Dict[str, Any] = Field(..., alias="schema")

class QueryRequest(BaseModel):
    save_name: str
    question: str
    top_k: int
    margin: float

class QueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
