"""Reset only the four project-owned example configs; no user projects are touched."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import ROOT
configs={'python/config.json':'{"module":"jsno"}\n','node/config.json':'{"proxyTarget":"http://127.0.0.1:9999"}\n'}
for relative,text in configs.items():
    path=(ROOT/'examples'/relative).resolve()
    if not path.is_relative_to((ROOT/'examples').resolve()):raise ValueError('Reset target outside examples')
    path.write_text(text,encoding='utf-8')
java=ROOT/'examples/java/config/application.properties';java.write_text(java.read_text(encoding='utf-8').replace('mysql:3306/','mysql:3307/'),encoding='utf-8')
nginx=ROOT/'examples/deployment/config/default.conf';nginx.write_text(nginx.read_text(encoding='utf-8').replace('backend:8000','backend:8001'),encoding='utf-8')
print('Four example configs reset. Restart registered demo containers to reproduce Java/Nginx failures.')
