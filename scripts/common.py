import glob, json, re, time, urllib.request, urllib.error

def load_keys(retries=20, wait=1.0):
    """プロジェクトの鍵ファイルを読む。同期の合間に空になることがあるのでやり直す。"""
    for _ in range(retries):
        keys = {}
        for p in glob.glob('/mnt/project/sns_keys*') + glob.glob('/tmp/sns_keys*') + glob.glob('./sns_keys*'):
            try:
                for line in open(p, encoding='utf-8', errors='ignore'):
                    m = re.match(r'\s*([A-Z_]+)\s*=\s*(\S+)', line)
                    if m:
                        keys[m.group(1)] = m.group(2).strip('"\'')
            except OSError:
                pass
        if keys:
            try:
                import os; fd=os.open('/tmp/.keys_cache',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                os.write(fd,json.dumps(keys).encode()); os.close(fd)
            except OSError: pass
            return keys
        time.sleep(wait)
    try: return json.load(open('/tmp/.keys_cache'))
    except Exception: return {}

def http(method, url, headers=None, data=None, timeout=60):
    if data is not None and not isinstance(data, (bytes, str)):
        data = json.dumps(data).encode()
        headers = dict(headers or {}, **{'Content-Type': 'application/json'})
    if isinstance(data, str):
        data = data.encode()
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            try: return r.status, json.loads(body.decode())
            except Exception: return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        try: return e.code, json.loads(body.decode())
        except Exception: return e.code, body[:300].decode('utf-8', 'ignore')
    except Exception as e:
        return 0, {'error': type(e).__name__, 'detail': str(e)[:200]}

def scrub(o, keys):
    s = o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)
    for v in keys.values():
        if v: s = s.replace(v, '[MASKED]')
    return s
