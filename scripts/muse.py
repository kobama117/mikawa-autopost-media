import base64, json, urllib.request, urllib.error
from common import load_keys
def gen_bg(prompt, out_path, size="1024x1792", keys=None):
    k = (keys or load_keys())['META_MODEL_API_KEY']
    req = urllib.request.Request('https://api.meta.ai/v1/images/generations',
        data=json.dumps({"model": "muse-image-1.0", "prompt": prompt, "n": 1, "size": size}).encode(),
        headers={'Authorization': 'Bearer ' + k, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=240) as r:
        d = json.loads(r.read())['data'][0]
    if d.get('b64_json'): open(out_path, 'wb').write(base64.b64decode(d['b64_json']))
    else: urllib.request.urlretrieve(d['url'], out_path)
    return out_path
