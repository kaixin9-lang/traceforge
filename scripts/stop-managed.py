import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.db import db
from traceforge.services import stop_host
for service in db.list('service'):
    if service['kind']=='uvicorn':
        try:stop_host(service);print('Stopped managed service:',service['id'])
        except ValueError as e:print(str(e))
