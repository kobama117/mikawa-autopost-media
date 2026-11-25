#!/usr/bin/env python3
"""毎日の自動投稿。使い方:
  python3 daily.py pick              -> 今日の候補記事を1本選び、事実抜き出し用のJSONを出す
  python3 daily.py publish spec.json -> 投稿内容(spec)から画像・リールを作り、GitHub経由でインスタとスレッズに投稿
  環境変数 SNS_DRY_RUN=1 なら投稿せずに作成までで止める
"""
import sys, os, re, json, html, random, subprocess, datetime, shutil, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http, load_keys, scrub

REPO_DIR = os.environ.get('REPO_DIR', '/home/claude/mikawa-autopost-media')
RAW = 'https://raw.githubusercontent.com/kobama117/mikawa-autopost-media/main/'
JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).date()
REUSE_DAYS = 60

# 季節の重み（月: {キーワード: 倍率}）。ラッコキーワードの需要調査(2026-11-14)に基づく
SEASON = {
    11: {'紅葉': 4, 'イルミ': 3, '11月イベント': 3, '初詣': 1.5, '初日の出': 1.2, '12月イベント': 1.5, 'クリスマス': 2},
    12: {'イルミ': 4, '初詣': 4, '初日の出': 3, '12月イベント': 3, 'クリスマス': 3, '1月イベント': 2, '紅葉': 1},
    1: {'初詣': 4, '1月イベント': 3, '初日の出': 1, '3月イベント': 1},
    2: {'2月イベント': 3, 'お花見': 1.5, '3月イベント': 2},
}
GENERIC = {'観光': 1.2, 'スポット': 1.0, '公園': 1.0, 'イベント': 0.8, '動物園': 1.0, '歴史': 0.8, '路面電車': 0.8, '神社': 1.0, 'デート': 1.0, '遊ぶ': 1.0}
OFF_SEASON = ['お花見', '花火', '夏祭り', '海水浴', 'プール', '7月イベント', '8月イベント', '6月イベント', '5月イベント', '10月イベント', '3月イベント', '9月イベント']
MOOD_OK = re.compile('|'.join(list(GENERIC) + ['紅葉', 'イルミ', '初詣', '初日の出', 'お花見', 'イベント', 'クリスマス']))
FOOD_NG = re.compile('グルメ|ランチ|ラーメン|カレー|うどん|居酒屋|カフェ|レストラン|ホテル|ホテル|駐車場|バス|占い|手相|保育士|病院|クリニック|賃貸|転職')

def log(*a): print(*a, file=sys.stderr)

def load_history():
    p = os.path.join(REPO_DIR, 'data/history.json')
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return []

def recently_used(hist):
    cut = TODAY - datetime.timedelta(days=REUSE_DAYS)
    return {h['url'] for h in hist if datetime.date.fromisoformat(h['date']) >= cut}

def load_rewrites():
    """リライト済み記事の一覧(data/rewrites.json)。リライト用プロジェクトが更新する。"""
    try: return {r['url']: r for r in json.load(open(os.path.join(REPO_DIR, 'data/rewrites.json'), encoding='utf-8'))}
    except Exception: return {}

def fetch_toyohashi():
    out, page = [], 1
    while True:
        c, b = http('GET', f'https://toyohashi-info.sakura.ne.jp/wp-json/wp/v2/posts?per_page=100&page={page}&_fields=id,link,title,date,modified')
        if c != 200 or not isinstance(b, list) or not b: break
        out += b; page += 1
        if len(b) < 100: break
    return [{'source': 'toyohashi', 'id': p['id'], 'url': p['link'], 'title': html.unescape(p['title']['rendered']), 'modified': p['modified'][:10]} for p in out]

def score(c):
    t = c['title']
    if FOOD_NG.search(t) or not MOOD_OK.search(t): return 0
    month = TODAY.month
    s = 0
    for k, w in SEASON.get(month, {}).items():
        if k in t: s += w
    for k, w in GENERIC.items():
        if k in t: s += w
    if any(k in t for k in OFF_SEASON): s *= 0.1
    if '12選' in t or '選' in t: s *= 1.1
    return s

def clean_article(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>|<iframe.*?</iframe>', '', h, flags=re.S)
    h = re.sub(r'<h[1-4][^>]*>(.*?)</h[1-4]>', lambda m: '\n## ' + re.sub('<.*?>', '', m.group(1)) + '\n', h, flags=re.S)
    h = re.sub(r'<(br|/p|/li|/tr|/div)[^>]*>', '\n', h); h = re.sub(r'<.*?>', '', h); h = html.unescape(h)
    # Googleマップの口コミ（他人の文章）と料金定型文は事実の素材から外す
    h = re.sub(r'📣 実際の利用者の声.*?Googleマップで全ての口コミを見る →', '', h, flags=re.S)
    h = re.sub(r'料金目安[^\n]*', '', h)
    return re.sub(r'\n\s*\n+', '\n', h).strip()

def cmd_pick():
    hist = load_history(); used = recently_used(hist)
    cands = [c for c in fetch_toyohashi() if c['url'] not in used]
    rew = load_rewrites()
    for c in cands:
        c['score'] = score(c)
        if c['url'] in rew and c['score'] > 0:
            c['score'] *= 1.6; c['rewritten'] = rew[c['url']].get('date')
    cands = sorted([c for c in cands if c['score'] > 0], key=lambda c: -c['score'])
    if not cands:
        print(json.dumps({'error': 'no_candidate'}, ensure_ascii=False)); return
    pool = cands[:3] if random.random() < 0.8 else cands[3:15] or cands[:3]
    pick = random.choice(pool[:2] if pool is cands[:3] else pool)
    c, b = http('GET', f"https://toyohashi-info.sakura.ne.jp/wp-json/wp/v2/posts/{pick['id']}?_fields=content,modified")
    text = clean_article(b['content']['rendered'])
    heads = re.findall(r'^## (.+)$', text, flags=re.M)
    print(json.dumps({'candidate': pick, 'top_candidates': [(x['title'], round(x['score'], 1)) for x in cands[:6]],
                      'headings': heads[:30], 'article_text': text[:7000], 'today': str(TODAY),
                      'suggested_format': 'reel' if TODAY.weekday() == 6 else 'carousel'}, ensure_ascii=False, indent=1))

def validate_carousel(spec):
    errs = []
    for k in ('source', 'post_id', 'url', 'title', 'tag', 'slides', 'cta_heading', 'cta_name', 'cta_text', 'bg_prompt', 'ig_caption', 'threads_text', 'slug'):
        if not spec.get(k): errs.append('missing ' + k)
    if errs: return errs
    if len(spec['title']) > 14: errs.append('title too long (<=14)')
    if len(spec['tag']) > 16: errs.append('tag too long (<=16)')
    sl = spec['slides']
    if not 3 <= len(sl) <= 7: errs.append('slides must be 3-7')
    ng = re.compile(r'\d[\d,]*円|料金|営業時間|口コミ|ランキング')
    for i, s in enumerate(sl):
        if len(s.get('heading', '')) > 14: errs.append(f'slide{i+1} heading too long (<=14)')
        its = s.get('items') or []
        if not 1 <= len(its) <= 3: errs.append(f'slide{i+1} items must be 1-3')
        for it in its:
            if len(it.get('name', '')) > 14: errs.append(f'slide{i+1} name too long (<=14)')
            if len(it.get('text', '')) > 40: errs.append(f'slide{i+1} text too long (<=40)')
            if ng.search(it.get('name', '') + it.get('text', '')): errs.append(f'slide{i+1} has price/hours/reviews')
    if 'AI生成' not in spec['ig_caption'] or 'AI生成' not in spec['threads_text']: errs.append('AI note missing')
    if re.search(r'https?://', spec['ig_caption']): errs.append('url in ig caption')
    if spec['url'] not in spec['threads_text']: errs.append('article url missing in threads')
    if len(spec['threads_text']) > 480: errs.append('threads too long')
    if len(spec['ig_caption']) > 2000: errs.append('ig too long')
    if not re.fullmatch(r'[a-z0-9\-]+', spec['slug']): errs.append('slug must be [a-z0-9-]')
    return errs

def validate(spec):
    if 'slides' in spec: return validate_carousel(spec)
    errs = []
    for k in ('source', 'post_id', 'url', 'title', 'tag', 'fact', 'bg_prompt', 'ig_caption', 'threads_text', 'slug'):
        if not spec.get(k): errs.append('missing ' + k)
    if errs: return errs
    if len(spec['title']) > 14: errs.append('title too long (<=14)')
    if len(spec['tag']) > 16: errs.append('tag too long (<=16)')
    if len(spec['fact']) > 30: errs.append('fact too long (<=30)')
    if 'AI生成' not in spec['ig_caption'] or 'AI生成' not in spec['threads_text']: errs.append('AI note missing')
    if re.search(r'https?://', spec['ig_caption']): errs.append('url in ig caption')
    if spec['url'] not in spec['threads_text']: errs.append('article url missing in threads')
    if len(spec['threads_text']) > 480: errs.append('threads too long')
    if len(spec['ig_caption']) > 2000: errs.append('ig too long')
    if not re.fullmatch(r'[a-z0-9\-]+', spec['slug']): errs.append('slug must be [a-z0-9-]')
    if re.search(r'料金|円|営業時間|口コミ', spec['fact'] + spec['tag'] + spec['title']): errs.append('no price/hours/reviews in overlay')
    return errs

def git(*args, check=True):
    return subprocess.run(['git', '-C', REPO_DIR, *args], check=check, capture_output=True, text=True)

def ensure_repo(keys):
    if not os.path.isdir(os.path.join(REPO_DIR, '.git')):
        url = f"https://x-access-token:{keys['GITHUB_TOKEN']}@github.com/kobama117/mikawa-autopost-media.git"
        r = subprocess.run(['git', 'clone', '--depth', '1', url, REPO_DIR], capture_output=True, text=True)
        if r.returncode: raise RuntimeError('clone failed: ' + scrub(r.stderr, keys)[:300])
    git('config', 'user.email', 'autopost@example.com'); git('config', 'user.name', 'autopost')
    git('pull', '--rebase', '-q', check=False)

def push(msg, keys):
    git('add', '-A'); git('commit', '-qm', msg, check=False)
    for _ in range(2):
        r = git('push', 'origin', 'HEAD:main', check=False)
        if r.returncode == 0 or 'new branch' in r.stderr or 'main -> main' in r.stderr: return
        url = f"https://x-access-token:{keys['GITHUB_TOKEN']}@github.com/kobama117/mikawa-autopost-media.git"
        r = subprocess.run(['git', '-C', REPO_DIR, 'push', url, 'HEAD:main'], capture_output=True, text=True)
        if r.returncode == 0: return
    raise RuntimeError('push failed: ' + scrub(r.stderr, keys)[:300])

def title_used(hist, title, days=30):
    cut = TODAY - datetime.timedelta(days=days)
    return any(h.get('title') == title and datetime.date.fromisoformat(h['date']) >= cut for h in hist)

def claim(spec, fmt, keys):
    """投稿の直前に履歴へ『投稿中』を記録してpushする。途中で失敗しても再実行で二重投稿しないため。"""
    hist = load_history()
    hist.append({'date': str(TODAY), 'source': spec['source'], 'post_id': spec['post_id'], 'url': spec['url'], 'title': spec['title'], 'format': fmt, 'status': 'posting'})
    os.makedirs(os.path.join(REPO_DIR, 'data'), exist_ok=True)
    json.dump(hist, open(os.path.join(REPO_DIR, 'data/history.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    push(f'claim {TODAY}', keys)

def finish_history(url, res, extra):
    hist = load_history()
    for h in reversed(hist):
        if h['url'] == url and h['date'] == str(TODAY) and h.get('status') == 'posting':
            h.pop('status'); h.update(extra); h['instagram'] = res.get('instagram', {}).get('permalink'); h['threads'] = res.get('threads', {}).get('permalink')
            if not (h['instagram'] or h['threads']): h['status'] = 'failed'
            break
    json.dump(hist, open(os.path.join(REPO_DIR, 'data/history.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def cleanup_old(keys_dir, days=7):
    cut = TODAY - datetime.timedelta(days=days)
    base = os.path.join(REPO_DIR, keys_dir)
    if not os.path.isdir(base): return
    for f in os.listdir(base):
        m = re.match(r'(\d{4}-\d{2}-\d{2})_', f)
        if m and datetime.date.fromisoformat(m.group(1)) < cut:
            p = os.path.join(base, f); shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

def publish_carousel(spec, bg, work, dry, keys):
    import carousel
    rel = f"carousels/{TODAY}_{spec['slug']}"; outdir = os.path.join(REPO_DIR, rel)
    try: paths = carousel.build(spec, outdir, bg)
    except ValueError as e:
        print(json.dumps({'ok': False, 'validation_errors': [str(e)]}, ensure_ascii=False)); sys.exit(2)
    shutil.copy(paths[0], '/tmp/autopost_last_cover.jpg')
    res = {'ok': True, 'dry_run': dry, 'format': 'info_carousel', 'images': rel, 'count': len(paths), 'date': str(TODAY)}
    if dry:
        print(json.dumps(res, ensure_ascii=False)); return
    push(f'carousel {TODAY}', keys)
    urls = [RAW + rel + '/' + os.path.basename(p) for p in paths]
    for _ in range(12):
        c, _b = http('GET', urls[-1], timeout=60)
        if c == 200: break
        time.sleep(5)
    else: raise RuntimeError('raw url not reachable')
    from poster import post_ig_carousel, post_threads_carousel
    claim(spec, 'info_carousel', keys)
    for name, fn, arg in (('instagram', post_ig_carousel, spec['ig_caption']), ('threads', post_threads_carousel, spec['threads_text'])):
        try: res[name] = fn(urls, arg, keys=keys, dry=False)
        except Exception as e: res[name] = {'error': scrub(str(e), keys)[:300]}
    finish_history(spec['url'], res, {'format': 'info_carousel', 'images': rel})
    cleanup_old('carousels'); cleanup_old('reels')
    push(f'history {TODAY}', keys)
    print(json.dumps(res, ensure_ascii=False))

def cmd_publish(spec_path):
    spec = json.load(open(spec_path, encoding='utf-8'))
    errs = validate(spec)
    if errs: print(json.dumps({'ok': False, 'validation_errors': errs}, ensure_ascii=False)); sys.exit(2)
    dry = os.environ.get('SNS_DRY_RUN') == '1'
    keys = load_keys(); ensure_repo(keys)
    if spec['url'] in recently_used(load_history()) and os.environ.get('ALLOW_REUSE') != '1':
        print(json.dumps({'ok': False, 'error': 'article used within %d days' % REUSE_DAYS})); sys.exit(3)
    if title_used(load_history(), spec['title']) and os.environ.get('ALLOW_REUSE') != '1':
        print(json.dumps({'ok': False, 'validation_errors': ['同じtitleを30日以内に使用済み。別の切り口のtitleに変える（例: 「豊橋のデート夜景」）']}, ensure_ascii=False)); sys.exit(2)
    work = '/tmp/autopost_work'; shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    from muse import gen_bg; from make_reel import overlay, zoom_reel
    bg = os.path.join(work, 'bg.png')
    for i in range(3):
        try: gen_bg(spec['bg_prompt'], bg, keys=keys); break
        except Exception as e:
            log('bg retry', i, scrub(str(e), keys)); time.sleep(5)
    else: raise RuntimeError('image generation failed')
    if 'slides' in spec:
        return publish_carousel(spec, bg, work, dry, keys)
    card = os.path.join(work, 'card.png'); overlay(bg, card, spec['title'], spec['tag'], spec['fact'])
    rel = f"reels/{TODAY}_{spec['slug']}.mp4"; out = os.path.join(REPO_DIR, rel); os.makedirs(os.path.dirname(out), exist_ok=True)
    zoom_reel(card, out)
    shutil.copy(card, os.path.join('/tmp', 'autopost_last_card.png'))
    res = {'ok': True, 'dry_run': dry, 'video': rel, 'date': str(TODAY)}
    if dry:
        print(json.dumps(res, ensure_ascii=False)); return
    push(f'reel {TODAY}', keys)
    url = RAW + rel
    for _ in range(12):
        c, _b = http('GET', url, timeout=60)
        if c == 200: break
        time.sleep(5)
    else: raise RuntimeError('raw url not reachable')
    from poster import post_ig_reel, post_threads_video
    claim(spec, 'ai_mood_reel', keys)
    for name, fn, arg in (('instagram', post_ig_reel, spec['ig_caption']), ('threads', post_threads_video, spec['threads_text'])):
        try: res[name] = fn(url, arg, keys=keys, dry=False)
        except Exception as e: res[name] = {'error': scrub(str(e), keys)[:300]}
    finish_history(spec['url'], res, {'format': 'ai_mood_reel', 'video': rel})
    # 7日より古い動画を消す
    cut = TODAY - datetime.timedelta(days=7)
    for f in os.listdir(os.path.join(REPO_DIR, 'reels')):
        m = re.match(r'(\d{4}-\d{2}-\d{2})_', f)
        if m and datetime.date.fromisoformat(m.group(1)) < cut: os.remove(os.path.join(REPO_DIR, 'reels', f))
    push(f'history {TODAY}', keys)
    print(json.dumps(res, ensure_ascii=False))

if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == 'pick': cmd_pick()
    elif len(sys.argv) >= 3 and sys.argv[1] == 'publish': cmd_publish(sys.argv[2])
    else: print(__doc__)
