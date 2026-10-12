import asyncio
import os
import sys
from contextlib import AsyncExitStack
from langchain_mcp_adapters.client import MultiServerMCPClient
from .config import settings,ROOT
from .security import redact

class MCPHub:
    def __init__(self):
        self.client=None
        self.tools={}
        self.status={}
        self.lock=asyncio.Lock()

    async def connect(self):
        async with self.lock:
            safe_env={k:v for k,v in os.environ.items() if not any(s in k.lower() for s in ['key','password','secret','token'])}
            safe_env['PYTHONPATH']=str(ROOT)
            self.client=MultiServerMCPClient({
                'local':{'transport':'stdio','command':sys.executable,'args':['-m','traceforge.mcp_servers','local'],'env':safe_env,'cwd':str(ROOT)},
                'docs':{'transport':'streamable_http','url':settings.mcp_docs_url},
            })
            for name in ['local','docs']:
                try:
                    found=await asyncio.wait_for(self.client.get_tools(server_name=name),timeout=25)
                    self.tools.update({t.name:t for t in found})
                    self.status[name]={'ok':True,'tools':[t.name for t in found]}
                except Exception as e:self.status[name]={'ok':False,'error':redact(str(e))[:400]}
            return self.status

    async def call(self,name,**kwargs):
        if name not in self.tools:await self.connect()
        if name not in self.tools:raise RuntimeError('MCP 工具未连接: '+name)
        return await asyncio.wait_for(self.tools[name].ainvoke(kwargs),timeout=30)

hub=MCPHub()
