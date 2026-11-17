import subprocess, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
def find_font(weight='Black'):
    import glob
    c=[p for p in glob.glob('/usr/share/fonts/**/*CJK*', recursive=True) if weight in p and ('JP' in p or p.endswith('.ttc'))]
    return c[0] if c else '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc'
def overlay(bg_path, out_path, title, tag, fact, W=1080, H=1920):
    im=Image.open(bg_path).convert('RGB')
    r=max(W/im.width,H/im.height); im=im.resize((int(im.width*r)+1,int(im.height*r)+1))
    l=(im.width-W)//2; t=(im.height-H)//2; im=im.crop((l,t,l+W,t+H))
    # 下と中央をやや暗くして文字を読みやすく
    dark=Image.new('RGB',(W,H),(0,0,0)); mask=Image.new('L',(W,H),0); d=ImageDraw.Draw(mask)
    for y in range(H):
        a=int(110*max(0,1-abs(y-H*0.42)/(H*0.30)))+int(120*max(0,(y-H*0.78)/(H*0.22)))
        d.line([(0,y),(W,y)],fill=min(a,170))
    im=Image.composite(dark,im,mask)
    dr=ImageDraw.Draw(im)
    fb=ImageFont.truetype(find_font('Black'),150,index=0)
    ft=ImageFont.truetype(find_font('Medium'),52,index=0)
    ff=ImageFont.truetype(find_font('Medium'),46,index=0)
    def center(txt,font,y,fill='white',shadow=True):
        size=font.size
        while dr.textlength(txt,font=font)>W*0.86 and size>24:
            size-=4; font=ImageFont.truetype(font.path,size,index=0)
        w=dr.textlength(txt,font=font)
        x=(W-w)/2
        if shadow: dr.text((x+4,y+4),txt,font=font,fill=(0,0,0),)
        dr.text((x,y),txt,font=font,fill=fill)
    center(title,fb,int(H*0.38))
    center(tag,ft,int(H*0.38)+210,fill=(255,230,200))
    center(fact,ff,int(H*0.86))
    center('※画像はイメージ（AI生成）',ImageFont.truetype(find_font('Medium'),34,index=0),int(H*0.94),fill=(230,230,230))
    im.save(out_path)
def zoom_reel(img, out, secs=9, fps=30):
    n=secs*fps
    vf=f"scale=2160:3840,zoompan=z='1+0.12*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s=1080x1920:fps={fps},format=yuv420p"
    subprocess.run(['ffmpeg','-y','-loglevel','error','-loop','1','-i',img,'-vf',vf,'-t',str(secs),'-c:v','libx264','-preset','veryfast','-crf','21','-movflags','+faststart','-an',out],check=True)
if __name__=='__main__':
    overlay('test_muse.png','test_card.png','浜松の紅葉','秋の絶景スポット','色づく木々を楽しめる')
    zoom_reel('test_card.png','test_reel.mp4')
