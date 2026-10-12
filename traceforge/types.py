from typing import Literal
from pydantic import BaseModel, Field,ConfigDict

class Evidence(BaseModel):
    id: str
    title: str
    content: str
    source: str
    kind: str = 'document'
    metadata: dict = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)

class Finding(BaseModel):
    title: str
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal['supported', 'hypothesis'] = 'hypothesis'

class RepairProposal(BaseModel):
    kind: Literal['patch', 'dependencies', 'restart', 'sandbox']
    title: str
    description: str
    workspace_id: str
    file: str = ''
    replacement: str = ''
    expected_hash: str = ''
    command: str = ''
    network: bool = False
    service: str = ''
    verify_command: str = ''
    runtime: Literal['python', 'node', 'java'] = 'python'

class Diagnosis(BaseModel):
    summary: str
    findings: list[Finding]
    next_steps: list[str]
    repairs: list[RepairProposal] = Field(default_factory=list)

class RunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=50000)
    workspace_id: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    mode: Literal['diagnose', 'knowledge'] = 'diagnose'

class ApprovalDecision(BaseModel):
    decision: Literal['approve', 'edit', 'reject']
    payload_hash: str
    edited_proposal: RepairProposal | None = None

class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=12000)
    strategy: Literal['dense', 'sparse', 'hybrid'] = 'hybrid'
    fusion: Literal['rrf', 'weighted'] = 'rrf'
    rerank: bool = True
    mmr: bool = False
    query_mode: Literal['original', 'rewrite', 'hyde', 'multi'] = 'original'
    workspace_id: str | None = None
    stack: str = ''
    version: str = ''
    top_k: int = Field(default=5, ge=1, le=20)

class WorkspaceRequest(BaseModel):
    name: str
    path: str
    stack: str = 'auto'

class ServiceRegistration(BaseModel):
    kind: Literal['container','uvicorn']
    name: str = ''
    container: str = ''
    module: str = 'main:app'
    port: int = Field(default=8100,ge=1024,le=65535)
    health_path: str = '/health'

class URLImport(BaseModel):
    url: str
    stack: str = 'general'
    version: str = ''
    workspace_id: str = 'global'

class EvaluationRequest(BaseModel):
    limit: int = Field(default=30, ge=1, le=30)
    ragas: bool = True

class RetrievalResponse(BaseModel):
    queries: list[str]
    routes: dict
    before_rerank: list[dict]
    evidence: list[Evidence]
    warnings: list[str]
    elapsed_ms: int
    config: dict

class RunRecord(BaseModel):
    model_config=ConfigDict(extra='allow')
    id: str
    thread_id: str
    query: str
    mode: str
    status: str
    created: float
    report: str = ''
    evidence: list[Evidence] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None
