from fastapi import FastAPI
app=FastAPI(title='TraceForge managed host demo')
@app.get('/health')
def health():
    return {'ok':True,'service':'managed-host-demo'}
