import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.providers import milvus_health

if __name__=='__main__':
    check=milvus_health()
    print(check['detail'])
    raise SystemExit(0 if check['ok'] else 1)
