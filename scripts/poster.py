import os, time, urllib.parse
from common import http, load_keys, scrub
IG_ID = '17841407039487048'
GV = 'https://graph.facebook.com/v21.0'
TV = 'https://graph.threads.net/v1.0'
FORM = {'Content-Type': 'application/x-www-form-urlencoded'}
def _form(d): return urllib.parse.urlencode(d)

def post_ig_reel(video_url, caption, keys=None, dry=None):
    keys = keys or load_keys(); t = keys['FB_GRAPH_TOKEN']
    if dry if dry is not None else os.environ.get('SNS_DRY_RUN') == '1':
        return {'dry_run': True, 'video_url': video_url, 'caption': caption}
    c, b = http('POST', f'{GV}/{IG_ID}/media', FORM, _form({'media_type': 'REELS', 'video_url': video_url, 'caption': caption, 'share_to_feed': 'true', 'access_token': t}))
    if c != 200: raise RuntimeError('ig create ' + scrub(b, keys)[:300])
    cid = b['id']
    for _ in range(40):
        time.sleep(6)
        c, s = http('GET', f'{GV}/{cid}?fields=status_code,status&access_token={t}')
        sc = s.get('status_code') if isinstance(s, dict) else None
        if sc == 'FINISHED': break
        if sc in ('ERROR', 'EXPIRED'): raise RuntimeError('ig media ' + scrub(s, keys)[:300])
    else: raise RuntimeError('ig media timeout')
    c, b = http('POST', f'{GV}/{IG_ID}/media_publish', FORM, _form({'creation_id': cid, 'access_token': t}))
    if c != 200: raise RuntimeError('ig publish ' + scrub(b, keys)[:300])
    mid = b['id']
    c, p = http('GET', f'{GV}/{mid}?fields=permalink&access_token={t}')
    return {'id': mid, 'permalink': p.get('permalink') if isinstance(p, dict) else None}

def post_threads_video(video_url, text, keys=None, dry=None):
    keys = keys or load_keys(); t = keys['THREADS_TOKEN']
    if dry if dry is not None else os.environ.get('SNS_DRY_RUN') == '1':
        return {'dry_run': True, 'video_url': video_url, 'text': text}
    c, b = http('POST', f'{TV}/me/threads', FORM, _form({'media_type': 'VIDEO', 'video_url': video_url, 'text': text, 'access_token': t}))
    if c != 200: raise RuntimeError('threads create ' + scrub(b, keys)[:300])
    cid = b['id']
    for _ in range(40):
        time.sleep(6)
        c, s = http('GET', f'{TV}/{cid}?fields=status,error_message&access_token={t}')
        st = s.get('status') if isinstance(s, dict) else None
        if st == 'FINISHED': break
        if st in ('ERROR', 'EXPIRED'): raise RuntimeError('threads media ' + scrub(s, keys)[:300])
    else: raise RuntimeError('threads media timeout')
    c, b = http('POST', f'{TV}/me/threads_publish', FORM, _form({'creation_id': cid, 'access_token': t}))
    if c != 200: raise RuntimeError('threads publish ' + scrub(b, keys)[:300])
    mid = b['id']
    c, p = http('GET', f'{TV}/{mid}?fields=permalink&access_token={t}')
    return {'id': mid, 'permalink': p.get('permalink') if isinstance(p, dict) else None}
