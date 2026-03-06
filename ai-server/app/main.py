from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import incidents, kb, rag, predictive, aiops, reporting

app = FastAPI(
    title="Smart Glass AI System API",
    description="Refactored API based on Detailed Incident and AIOps Specifications",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# New Router Mappings
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["A. Incident Management"])
app.include_router(kb.router, prefix="/api/v1/kb", tags=["B. Knowledge Base"])
app.include_router(rag.router, prefix="/api/v1/rag", tags=["C. RAG Engine"])
app.include_router(predictive.router, prefix="/api/v1/predict", tags=["D. Predictive AI"])
app.include_router(aiops.router, prefix="/api/v1/aiops", tags=["E. AIOps"])
app.include_router(reporting.router, prefix="/api/v1/report", tags=["F. Reporting"])

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}
