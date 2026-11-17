"""情報カードのカルーセル(4:5, 1080x1350, JPEG)を作る。表紙だけAI背景、中身は文字カード。"""
import os, glob
from PIL import Image, ImageDraw, ImageFont
W, H = 1080, 1350

def font(weight, size):
    c = [p for p in glob.glob('/usr/share/fonts/**/*CJK*', recursive=True) if weight in p]
    return ImageFont.truetype(c[0] if c else '/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc', size, index=0)

def wrap(draw, text, f, maxw):
    lines, cur = [], ''
    for ch in text:
        if draw.textlength(cur + ch, font=f) > maxw and cur and ch not in '。、」）！？':
            lines.append(cur); cur = ch
        else: cur += ch
    if cur: lines.append(cur)
    return lines

def gradient(top, bottom):
    im = Image.new('RGB', (W, H)); d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H; d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return im

def cover(bg_path, out, title, tag, total):
    im = Image.open(bg_path).convert('RGB')
    r = max(W / im.width, H / im.height); im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
    l = (im.width - W) // 2; t = (im.height - H) // 2; im = im.crop((l, t, l + W, t + H))
    dark = Image.new('RGB', (W, H), (0, 0, 0)); mask = Image.new('L', (W, H), 0); md = ImageDraw.Draw(mask)
    for y in range(H):
        a = int(130 * max(0, 1 - abs(y - H * 0.5) / (H * 0.32))) + int(110 * max(0, (y - H * 0.82) / (H * 0.18)))
        md.line([(0, y), (W, y)], fill=min(a, 170))
    im = Image.composite(dark, im, mask); d = ImageDraw.Draw(im)
    def center(txt, f0, y, fill='white'):
        f = f0
        while d.textlength(txt, font=f) > W * 0.86 and f.size > 24: f = font_like(f0, f.size - 4)
        x = (W - d.textlength(txt, font=f)) / 2
        d.text((x + 4, y + 4), txt, font=f, fill=(0, 0, 0)); d.text((x, y), txt, font=f, fill=fill)
    def font_like(f0, size): return ImageFont.truetype(f0.path, size, index=0)
    center(title, font('Black', 140), int(H * 0.42)); center(tag, font('Medium', 56), int(H * 0.42) + 200, (255, 230, 200))
    center('保存して週末の参考に', font('Medium', 44), int(H * 0.80), (255, 255, 255))
    d.text((W - 150, 40), f'1/{total}', font=font('Medium', 36), fill=(255, 255, 255))
    d.text((40, H - 70), '※背景はイメージ（AI生成）', font=font('Medium', 30), fill=(230, 230, 230))
    im.save(out, quality=92)

def content(out, heading, items, idx, total, palette):
    top, bottom, accent = palette
    im = gradient(top, bottom); d = ImageDraw.Draw(im)
    d.text((W - 150, 40), f'{idx}/{total}', font=font('Medium', 36), fill=(255, 255, 255))
    fh = font('Black', 84); y = 130
    for ln in wrap(d, heading, fh, W - 160): d.text((80, y), ln, font=fh, fill='white'); y += 108
    d.line([(80, y + 10), (260, y + 10)], fill=accent, width=8); y += 60
    fn, ft = font('Black', 68), font('Medium', 48)
    for it in items:
        d.text((80, y), '■ ' + it['name'], font=fn, fill=accent); y += 96
        for ln in wrap(d, it['text'], ft, W - 180): d.text((110, y), ln, font=ft, fill=(255, 255, 255)); y += 68
        y += 64
    return im.save(out, quality=92)

PALETTES = [((74, 28, 22), (140, 52, 30), (255, 214, 150)), ((34, 58, 44), (70, 100, 60), (255, 226, 150)),
            ((52, 36, 70), (100, 52, 80), (255, 210, 170)), ((60, 40, 24), (130, 80, 36), (255, 224, 160))]

def build(spec, outdir, bg_path):
    os.makedirs(outdir, exist_ok=True)
    slides = spec['slides']; total = len(slides) + 2
    paths = []
    p = os.path.join(outdir, '01.jpg'); cover(bg_path, p, spec['title'], spec['tag'], total); paths.append(p)
    for i, s in enumerate(slides):
        p = os.path.join(outdir, f'{i + 2:02d}.jpg'); content(p, s['heading'], s['items'], i + 2, total, PALETTES[i % len(PALETTES)]); paths.append(p)
    # 最後の案内カード
    p = os.path.join(outdir, f'{total:02d}.jpg')
    content(p, spec['cta_heading'], [{'name': spec['cta_name'], 'text': spec['cta_text']}], total, total, ((30, 30, 30), (80, 40, 30), (255, 214, 150))); paths.append(p)
    return paths
