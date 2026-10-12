from pathlib import Path
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / '.env'), extra='ignore')
    deepseek_api_key: str = ''
    deepseek_model: str = 'deepseek-flash'
    deepseek_proxy_url: str = ''
    ollama_url: str = 'http://127.0.0.1:11434'
    embedding_model: str = 'qwen3-embedding:0.6b'
    rerank_model_path: str = 'D:/python_program/RAG_Agent/models/Qwen3-Reranker-0.6B'
    rerank_device: str = 'cuda'
    milvus_uri: str = 'http://127.0.0.1:19530'
    mcp_docs_url: str = 'http://127.0.0.1:8001/mcp'
    wsl_distro: str = 'Ubuntu'
    data_dir: Path = ROOT / 'data'
    collection: str = 'traceforge_chunks_v1'
    max_model_calls: int = 16
    max_iterations: int = 2

settings = Settings()
os.environ.setdefault('LANGGRAPH_STRICT_MSGPACK','true')
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
settings.data_dir.mkdir(parents=True, exist_ok=True)
