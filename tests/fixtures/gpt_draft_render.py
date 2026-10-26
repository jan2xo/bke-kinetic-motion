import os,sys,json,math,random,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'skill/bke-kinetic-motion/scripts'))
import mglib as mg
T=json.loads((ROOT/'timeline.json').read_text())
E={e['id']:e['t'] for e in T['events']}
W,H=360,640
mg.configure(W=W,H=H,S=1,FPS=T['fps'])
F=mg.font
G=(255,194,40); WHITE=(245,246,248)
CARD=[mg.media_card(['video','image','audio','folder'][i%4],seed=i,w=118,h=78 if i%4!=2 else 52) for i in range(15)]
# Reference renderer reused: mglib media_card(), transform_card(), easing and Montserrat font.
random.seed(25)
COORD=[(random.uniform(-180,470),random.uniform(60,590),random.uniform(.48,1.35),random.uniform(-20,20)) for i in range(15)]
def clamp(v):return max(0,min(1,v))
def progress(t,a,d):return clamp((t-a)/d)
def expo(t,a,d):return mg.eo(progress(t,a,d))
def cubic(t,a,d):return mg.eio(progress(t,a,d))
def text(draw,s,x,y,size=32,weight='Black',color=WHITE,anchor='mm',spacing=0):
    f=F(weight,size);draw.text((x,y),s,font=f,fill=color,anchor=anchor,stroke_width=0)
def base(t):
    im=Image.new('RGB',(W,H),(7,10,15)); d=ImageDraw.Draw(im)
    for y in range(0,H,3):
        k=max(0,1-abs(y/H-.45)*1.6);c=int(7+8*k);d.line((0,y,W,y),fill=(c,c+3,c+7))
    for x in range(20,W,46):d.line((x,0,x,H),fill=(20,25,30),width=1)
    for y in range(28,H,46):d.line((0,y,W,y),fill=(20,25,30),width=1)
    d.line((22,48,338,48),fill=(65,68,71),width=1)
    text(d,'BKE / RENDER DOCK',22,28,11,'Bold',anchor='lm',color=(185,190,196))
    text(d,'PRODUCTION / 01',338,28,9,'Medium',anchor='rm',color=(128,134,140))
    return im

def cardpaste(im,card,x,y,scale=1,angle=0,opacity=1):
    if opacity<=0:return
    layer=mg.transform_card(card,max(.12,scale),angle,opacity)
    im.paste(layer,(int(x-layer.width/2),int(y-layer.height/2)),layer)

def ui_frame(im,y0=200):
    d=ImageDraw.Draw(im,'RGBA');d.rounded_rectangle((27,y0,333,y0+280),radius=13,fill=(19,23,30,246),outline=(91,98,107,180),width=2)
    d.rounded_rectangle((38,y0+13,322,y0+53),radius=7,fill=(31,36,43,255))
    text(d,'RENDER QUEUE',53,y0+34,15,'Bold',anchor='lm')
    text(d,'03 JOBS',310,y0+34,10,'Bold',color=G,anchor='rm')

def frame(t):
    im=base(t);d=ImageDraw.Draw(im,'RGBA')
    # scene 1: depth disorder; one card selected, camera approaches
    if t<3.15:
        dolly=cubic(t,E['camera_chaos'],2)
        for i,(x,y,z,r) in sorted(enumerate(COORD),key=lambda q:q[1][2]):
            drift=math.sin(t*(1.0+i*.05)+i)*10
            sc=z*(1+.15*dolly)
            alpha=clamp((3.08-t)/.3) if t>2.7 else 1
            cardpaste(im,CARD[i],x+(180-x)*dolly*.20+drift,y+(320-y)*dolly*.14,sc,r*(1-dolly*.55),alpha)
        a=expo(t,E['title_chaos'],.5)
        if a>0:
            d=ImageDraw.Draw(im,'RGBA');d.rounded_rectangle((18,262,342,374),radius=8,fill=(5,8,12,int(230*a)))
            text(d,'TOO MANY',180,301+24*(1-a),39,'Black',anchor='mm')
            text(d,'FILES?',180,342+24*(1-a),53,'Black',color=G,anchor='mm')
    # scene 2: intake, actual media tile to drop zone
    if 3<=t<6.12:
        d=ImageDraw.Draw(im,'RGBA');d.rounded_rectangle((28,175,332,405),radius=17,fill=(22,27,34,245),outline=G+(210,),width=2)
        d.rounded_rectangle((44,204,316,353),radius=10,fill=(11,15,21,220),outline=(91,102,114,150),width=2)
        text(d,'DROP MEDIA HERE',180,319,15,'Bold',anchor='mm',color=(210,213,220))
        p=expo(t,E['discovery'],.5)
        cardpaste(im,CARD[0],180,150+104*p,1.05-.26*p,0,1)
        if t>=E['text_drag']:
            text(d,'DRAG.',180,470+35*(1-expo(t,E['text_drag'],.5)),41,'Black',anchor='mm')
        if t>=E['text_drop']:
            text(d,'DROP.',180,526+35*(1-expo(t,E['text_drop'],.5)),41,'Black',color=G,anchor='mm')
        if t>=E['camera_lane']:
            k=cubic(t,E['camera_lane'],1)
            d.line((180,401,180,401+140*k),fill=G+(190,),width=3)
    # scene 3: queue
    if 6<=t<9.15:
        ui_frame(im,180)
        d=ImageDraw.Draw(im,'RGBA')
        for j,(name,status) in enumerate([('Launch_01.mp4','COMPLETE'),('Scene_02.mov','RENDERING'),('Social_Cut.mp4','QUEUED')]):
            y=255+j*66
            p=expo(t,E['grid_impact']+j*.12,.5)
            if p<=0:continue
            x=43+int((1-p)*250)
            d.rounded_rectangle((x,y,x+273,y+55),radius=8,fill=(37,43,51,int(245*p)),outline=(74,80,88,int(190*p)))
            text(d,name,x+12,y+17,12,'Bold',anchor='lm')
            text(d,status,x+12,y+37,9,'Medium',color=G if j==0 else (160,170,181),anchor='lm')
            d.rounded_rectangle((x+176,y+29,x+254,y+35),radius=3,fill=(67,71,78,240))
            frac=1 if j==0 else (progress(t,E['progress'],1.0) if j==1 else .04)
            d.rounded_rectangle((x+176,y+29,x+176+max(2,int(78*frac)),y+35),radius=3,fill=G+(255,))
        if t>=E['text_organize']:
            text(d,'ORGANIZE.',180,524,32,'Black',anchor='mm')
        if t>=E['text_render']:
            text(d,'RENDER.',180,572,39,'Black',color=G,anchor='mm')
    # scene 4: delivery
    if 9<=t<12.12:
        d=ImageDraw.Draw(im,'RGBA')
        d.rounded_rectangle((42,192,318,420),radius=16,fill=(24,30,38,255),outline=(87,94,104,200),width=2)
        cardpaste(im,CARD[0],180,285,1.72,0,1)
        d.ellipse((280,382,306,408),fill=G+(255,))
        text(d,'✓',293,395,18,'Bold',color=(8,13,19),anchor='mm')
        if t>=E['text_ready']:
            text(d,'READY TO',180,489,32,'Black',anchor='mm')
            text(d,'DELIVER.',180,535,40,'Black',color=G,anchor='mm')
        if t>=E['output_line']:
            p=cubic(t,E['output_line'],.5)
            d.line((85,579,85+190*p,579),fill=G+(230,),width=3)
    # scene 5: premium static end, no HUD
    if t>=12:
        im=Image.new('RGB',(W,H),(8,10,14));d=ImageDraw.Draw(im,'RGBA')
        # reserved gold edge light and faint inner radial composition
        for rad in range(170,30,-8):
            a=int(1.2*(170-rad)/140)
            d.ellipse((180-rad,300-rad,180+rad,300+rad),outline=(255,194,40,a),width=2)
        p=expo(t,E['hero'],1.0)
        if p>0:
            y=300+(1-p)*80
            text(d,'RENDER',180,y-30,52,'Black',anchor='mm')
            text(d,'DOCK',180,y+31,71,'Black',color=G,anchor='mm')
            d.line((90,y+88,90+180*p,y+88),fill=G+(255,),width=3)
            if t>=E['hero_settle']:
                a=expo(t,E['hero_settle'],.5)
                text(d,'By BKE',180,y+130+(1-a)*18,21,'Bold',anchor='mm',color=(215,217,220,int(255*a)))
        if t<12.15:
            strength=(1-progress(t,12,.15))**2
            d.rectangle((0,0,W,H),fill=(255,222,145,int(75*strength)))
    return im

def main():
    out=ROOT/'draft';out.mkdir(exist_ok=True)
    # A true low-resolution draft at locked 30fps, rather than misleading upscale.
    cmd=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(T['fps']),'-i','-','-c:v','libx264','-preset','veryfast','-crf','17','-pix_fmt','yuv420p',str(out/'silent.mp4')]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    for i in range(round(T['duration']*T['fps'])):
        im=frame(i/T['fps'])
        proc.stdin.write(im.tobytes())
        if i%75==0:
            im.save(out/f'frame_{i:03}.png');print('frame',i,flush=True)
    proc.stdin.close();ret=proc.wait()
    if ret:raise RuntimeError(f'ffmpeg {ret}')
    print('DRAFT VIDEO',out/'silent.mp4')
if __name__=='__main__':main()
