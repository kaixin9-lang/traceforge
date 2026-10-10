"""Demo contract: load the standard library JSON module; config should use 'json'."""
import importlib
import json
from pathlib import Path
config=json.loads(Path('config.json').read_text())
module=importlib.import_module(config['module'])
assert module.__name__=='json'
print('Python service configuration verified: JSON module available')
