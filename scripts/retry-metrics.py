import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.evaluation import Evaluator
from traceforge.types import EvaluationRequest
from traceforge.config import settings
from traceforge.db import db
async def main():
    id=(settings.data_dir/'evaluation-id.txt').read_text().strip()
    job=db.get('evaluation',id)
    await Evaluator().run(id,EvaluationRequest(limit=job['limit'],ragas=True))
    print(db.get('evaluation',id)['summary']['ragas'])
if __name__=='__main__':asyncio.run(main())
