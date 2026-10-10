import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
import socket

SECRET = re.compile(r'(?i)(sk-[\w-]{12,}|(?:api[_-]?key|password|passwd|secret|token|authorization)["\']?\s*[=:]\s*["\']?[^\s"\',;]+|Bearer\s+[\w.\-]+)')

def redact(value):
    if isinstance(value, str):
        return SECRET.sub('[已脱敏]', value)
    if isinstance(value, dict):
        return {k: '[已脱敏]' if re.search(r'(?i)password|api.?key|secret|token|authorization', k) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def within(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ':' in relative or relative.startswith(('\\', '/')):
        raise ValueError('必须使用项目内的相对路径')
    original=root / relative
    for part in [original,*original.parents]:
        if part==root:break
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):raise ValueError('不允许通过链接访问项目文件')
    target = original.resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('路径超出项目范围')
    if any(p in {'.git', '.venv', 'node_modules'} for p in target.relative_to(root.resolve()).parts) or target.name == '.env':
        raise ValueError('此路径不允许读取或修改')
    return target

def public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('仅支持公开 HTTPS 地址')
    for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError('禁止请求本地、内网或保留地址')
    return url
