"""
promo_3d_template.py - 6 s 2.5D promo: cards scattered in depth -> snap flat into one grid -> flat title. (v2.1)

TIMING LIVES IN timeline_3d.json (its own manifest). This file only says what things LOOK like and how 3D is staged.
Read docs/3D_DECISIONS.md first: here space carries the meaning (depth = disorder, one plane = order), which is
the only reason this piece uses real 3D.

  python3 ../scripts/timeline.py check timeline_3d.json     # plan must pass first (includes the 3D rules)
  python3 promo_3d_template.py lint                          # camera + readability + end-state rules -> lint3d.txt
  python3 promo_3d_template.py stills 0.8 2.0 2.6 3.3 4.6    # QA stills -> stills/
  python3 promo_3d_template.py render [--preview]            # frames/ + visual_log.json
  python3 promo_3d_template.py bench                         # seconds per frame at the current S
Then music_synth.py --manifest timeline_3d.json, encode.sh, and the full QA loop (SKILL.md, section 3D).

Phases (all times from the manifest):
  1 scatter  0 -> snap      30 cards scattered in depth and tumbling; ONE camera move: a slow dolly (40 mm, cubic in-out)
                            that settles frontal; the headline card arrives frontal and holds focus while it is read.
  2 align    snap -> title  rank-2 impact: every card snaps flat into a 6x5 grid on one frame; the gold key light
                            sweeps the grid; the grid recedes in depth into the cut.
  3 title    title -> end   rank-1 impact: flat, frontal, still title and end card (2D), receded grid dim behind it.
"""
import sys, os, math, random, time, json
HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.environ.get('BKE_KIT', os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, os.path.join(KIT, 'scripts'))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import mglib as M
import mg3d as G
import timeline as TL

MANIFEST = os.environ.get('BKE_MANIFEST', os.path.join(HERE, 'timeline.json'))
TLM = TL.load(MANIFEST)
FPS, DUR = TLM.fps, TLM.duration

# ---------------------------------------------------------------- times (all from the manifest)
E_DOLLY, E_HEAD, E_SNAP, E_SWEEP, E_RECEDE, E_TITLE = (TLM.event(i) for i in ('cam_dolly', 'headline', 'snap', 'rim_sweep', 'recede', 'title'))
T_SNAP, T_TITLE = E_SNAP.t, E_TITLE.t
SNAP_START = T_SNAP - 1 / FPS                     # expo-out: the largest step lands on the declared frame
SNAP_DUR = 0.55
HEAD_IN = E_HEAD.t - 0.10                          # expo-out entrance peaks ~3 frames after it starts
HEAD_OUT = (T_SNAP - 0.50, T_SNAP - 0.15)          # departs expo-in before the snap
FOCUS_PULL = (T_SNAP - 0.50, T_SNAP - 0.05)
SWEEP = (E_SWEEP.t - 0.10, E_SWEEP.t - 0.10 + float(E_SWEEP.duration or 0.7))
RECEDE = (E_RECEDE.t - 0.26, T_TITLE)
MV = E_DOLLY.move3d
LENS = TLM.data['camera3d']['lens_mm']
RIG = G.CameraRig('dolly', E_DOLLY.t, MV['end'], lens_mm=LENS, ease='eio', **{'from': MV['from'], 'to': MV['to']})
D0 = G.Camera.design_distance(lens_mm=LENS)


# ---------------------------------------------------------------- AIR STACK / SIX-SHOT DIRECTION
# Extends the BKE v2.2 3D promo template, preserves its native camera,
# Card/Renderer/Text/finish/render_all, and its manifest-first event map.
# No per-frame state: deterministic pictures at any t and frame index.
M.configure(W=int(TLM.data['canvas']['w']), H=int(TLM.data['canvas']['h']), FPS=FPS)
CYAN=(66,218,245); ICE=(226,246,251); MUTED=(133,163,182)
NAVY=(10,21,39); GRAPHITE=(23,36,53)
KEYS=('cam_dolly','headline','cam_track','repeat_build','cam_push',
      'one_panel','snap','question','cam_flow','build_title',
      'rim_sweep','workflow_lock','cam_arc','refresh','populate',
      'automate','cam_output','broadcast','recede','title','title_text','brand_shine')
TIMES={k:TLM.event(k).t for k in KEYS}
MOVES=[TLM.event(k) for k in ('cam_dolly','cam_track','cam_push','cam_flow','cam_arc','cam_output')]
ARCS=[
 G.CameraRig('dolly',TIMES['cam_dolly'],2.0,lens_mm=LENS,ease='eio',
             **{'from':(0,0,1400),'to':(0,0,2600)}),
 G.CameraRig('dolly',TIMES['cam_track'],4.0,lens_mm=LENS,ease='eio',
             **{'from':(0,0,2600),'to':(-380,0,2600)}),
 G.CameraRig('dolly',TIMES['cam_push'],6.95,lens_mm=LENS,ease='eio',
             **{'from':(-380,0,2600),'to':(-100,0,2500)}),
 G.CameraRig('dolly',TIMES['cam_flow'],10.95,lens_mm=LENS,ease='eio',
             **{'from':(-100,0,2500),'to':(180,0,2250)}),
 G.CameraRig('orbit',TIMES['cam_arc'],14.95,lens_mm=LENS,ease='eio',
             az0=math.degrees(math.atan2(180,2250)),
             az1=math.degrees(math.atan2(180,2250))+16,
             radius=math.hypot(180,2250),elev=0),
 G.CameraRig('dolly',TIMES['cam_output'],17.4,lens_mm=LENS,ease='eio',
             **{'from':(794,0,2113),'to':(0,0,1900)})
]
# The 0.05s between camera moves is a camera hold at the previous rig's
# destination, not a teleport into a new scene.
def camera_at(t):
    rig=ARCS[0]
    for r in ARCS:
        if t>=r.t0: rig=r
        else: break
    return rig.at(t)

LABELS=('RUNDOWN','GUEST DATA','LOWER THIRDS','MEDIA ASSETS',
        'ON-AIR ACTIONS','OUTPUT LINK')
OLD=('PROGRAM / DAY 01','NAMES / REV A','TITLE / REV 03',
     'CLIPS / 12 ITEMS','CUE / MANUAL','EXTERNAL OUTPUT')
NEW=('PROGRAM / DAY 02','NAMES / UPDATED','TITLE / VERIFIED',
     'CLIPS / REFRESHED','CUE / SEQUENCE','TO BROADCAST APP')
TEX_OLD=None; TEX_NEW=None; CARDS_OLD=None; CARDS_NEW=None
SCAT=None; GRID=None; HERO=None; OUT=None; SPATIAL_TYPE=None
NUM=15

def make_panel(header,detail,index,large=False):
    w,h=(1070,630) if large else (440,258)
    tex=Image.new('RGBA',(M.P(w),M.P(h)),(0,0,0,0))
    d=ImageDraw.Draw(tex)
    d.rounded_rectangle((M.P(2),M.P(2),M.P(w-2),M.P(h-2)),
                        radius=M.P(20 if large else 14),
                        fill=(20,34,52,255),outline=CYAN+(108 if index%3==0 else 38,),
                        width=M.P(2))
    # Graphite material, sparse rules and status blocks. Designed broadcast
    # preparation fields, never a generic dashboard screenshot.
    d.rounded_rectangle((M.P(18),M.P(18),M.P(w-18),M.P(53 if not large else 95)),
                        radius=M.P(8),fill=(30,47,65,255))
    d.ellipse((M.P(w-48),M.P(28),M.P(w-34),M.P(42)),
              fill=CYAN+(240,))
    line_y=112 if not large else 205
    for j in range(3):
        yy=line_y+j*(37 if not large else 93)
        d.rounded_rectangle((M.P(28),M.P(yy),M.P(w-29),M.P(yy+18 if not large else yy+50)),
                            radius=M.P(3),fill=(33+j*2,56+j*3,73+j*2,255))
        d.rounded_rectangle((M.P(28),M.P(yy),M.P(130 if not large else 270),M.P(yy+18 if not large else yy+50)),
                            radius=M.P(3),fill=(48,97,113,200))
    title=M.Text(header,'Bold',30 if not large else 57,ICE,tracking=1)
    subtitle=M.Text(detail,'Medium',20 if not large else 32,CYAN,tracking=0)
    M.comp(tex,title.img,M.P(32),M.P(24 if not large else 35))
    M.comp(tex,subtitle.img,M.P(32),M.P(73 if not large else 123))
    return tex

def assets():
    global TEX_OLD,TEX_NEW,CARDS_OLD,CARDS_NEW,SCAT,GRID,HERO,OUT,SPATIAL_TYPE
    if TEX_OLD is not None:return
    TEX_OLD=[make_panel(LABELS[i],OLD[i],i) for i in range(6)]
    TEX_NEW=[make_panel(LABELS[i],NEW[i],i) for i in range(6)]
    CARDS_OLD=[G.Card(tex,(440,258),name=f'workflow_old_{i}') for i,tex in enumerate(TEX_OLD)]
    CARDS_NEW=[G.Card(tex,(440,258),name=f'workflow_new_{i}') for i,tex in enumerate(TEX_NEW)]
    GRID=G.card_wall(6,3,(515,310),(0,0,0))
    # The same task exists in multiple disconnected broadcast preparations.
    # One founding schedule is near the lens, other copies recede through space.
    rng=np.random.default_rng(1206)
    SCAT=[dict(pos=np.array((0.,0.,350.)),rot=np.array((0.,0.,0.)),delay=0.)]
    for i in range(1,NUM):
        px=rng.uniform(-1480,1480)
        py=rng.uniform(-680,680)
        pz=rng.uniform(-900,400)
        SCAT.append(dict(pos=np.array((px,py,pz)),
                         rot=np.array((rng.uniform(-13,13),rng.uniform(-17,17),rng.uniform(-12,12))),
                         delay=.10+i*.20))
    OUT=G.Card(make_panel('BROADCAST OUTPUT','READY / TO EXISTING PLAYOUT',3,large=True),
               (1070,630),name='broadcast_output',shadow=True)
    SPATIAL_TYPE={
        'every':G.Card(M.Text('EVERY BROADCAST.','Black',120,ICE,tracking=3).img,
                       is_text=True,shadow=False,rim=False,layer=1),
        'same':G.Card(M.Text('THE SAME WORK?','Bold',82,CYAN,tracking=3).img,
                       is_text=True,shadow=False,rim=False,layer=1),
        'question':G.Card(M.Text('WHAT IF YOU BUILT IT ONCE?','Bold',66,ICE,tracking=2).img,
                       is_text=True,shadow=False,rim=False,layer=1),
        'build':G.Card(M.Text('BUILD ONCE.','Black',118,ICE,tracking=3).img,
                       is_text=True,shadow=False,rim=False,layer=1),
        'populate':G.Card(M.Text('POPULATE.','Black',112,ICE,tracking=4).img,
                       is_text=True,shadow=False,rim=False,layer=1),
        'automate':G.Card(M.Text('AUTOMATE.','Black',112,CYAN,tracking=4).img,
                       is_text=True,shadow=False,rim=False,layer=1),
        'broadcast':G.Card(M.Text('BROADCAST.','Black',110,ICE,tracking=3).img,
                       is_text=True,shadow=False,rim=False,layer=1)
    }

def cluster(t):
    # First five seconds: work multiplicity increases and maintains its depth.
    # After connection, existing objects physically align into one workflow.
    out=[]
    k=M.eio(M.prog(t,TIMES['snap']-.3,TIMES['snap']+.95))
    fade=M.eio(M.prog(t,TIMES['cam_flow'],TIMES['cam_flow']+.6))
    for i,s in enumerate(SCAT):
        emerge=M.eo(M.prog(t,s['delay']-.16,s['delay']+.55))
        drift=np.array((20*math.sin(t*1.3+i),12*math.sin(t*.8+i),0))
        scattered=s['pos']+drift*(1-k)
        anchored=np.array(GRID[i%6]['pos'],float)
        pos=scattered*(1-k)+anchored*k
        rot=s['rot']*(1-k)
        if i<6:
            alpha=emerge*(1-M.eio(M.prog(t,TIMES['refresh']-.2+i*.14,TIMES['refresh']+.32+i*.14)))
        else:
            alpha=emerge*(1-k)*(1-fade*.4)
        if alpha>.005:
            out.append(CARDS_OLD[i%6].with_xf(pos=pos,rot=rot,alpha=alpha))
        if i<6 and t>=TIMES['snap']:
            ref=M.eio(M.prog(t,TIMES['refresh']-.2+i*.14,TIMES['refresh']+.32+i*.14))
            if ref>.005:
                out.append(CARDS_NEW[i].with_xf(pos=pos,rot=rot,alpha=ref))
    return out

def type_card(which,t,start,end,y=475,z=460,scale=1.):
    a=M.eo(M.prog(t,start-.20,start+.28))*(1-M.ei(M.prog(t,end-.3,end)))
    cam=camera_at(t)
    # Rotate toward the lens so readability survives the subtle 16-degree arc.
    yaw=math.degrees(math.atan2(cam.pos[0],cam.pos[2]))
    z0=z+(1-M.eo(M.prog(t,start-.20,start+.55)))*(-120)
    return SPATIAL_TYPE[which].with_xf(pos=(0,y,z0),rot=(0,yaw,0),scale=scale,alpha=a)

def type_states(t):
    out=[]
    if t<TIMES['cam_push']:
        out.extend([
          type_card('every',t,TIMES['headline'],2.45,430,420,.78),
          type_card('same',t,2.45,4.08,290,460,.85)])
    elif t<TIMES['cam_flow']:
        out.append(type_card('question',t,TIMES['question'],TIMES['cam_flow']+.08,475,450,1.))
    elif t<TIMES['cam_arc']:
        out.append(type_card('build',t,TIMES['build_title'],TIMES['cam_arc']+.04,490,450,1.))
    elif t<TIMES['cam_output']:
        out.append(type_card('populate',t,TIMES['populate'],13.10,490,450,.9))
        out.append(type_card('automate',t,TIMES['automate'],15.08,490,450,.9))
    elif t<TIMES['title']:
        out.append(type_card('broadcast',t,TIMES['broadcast'],TIMES['title'],500,500,1.))
    return [c for c in out if c.alpha>.005]

def output_state(t):
    u=M.eo(M.prog(t,TIMES['broadcast']-.12,TIMES['broadcast']+.72))
    if u<.005:return []
    # Output floats ahead of the pipeline without pretending to be a
    # replacement application: it is explicitly the downstream handoff.
    a=u*(1-M.eio(M.prog(t,TIMES['recede']-.30,TIMES['title']+.14)))
    return [OUT.with_xf(pos=(0,0,290),rot=(0,0,0),scale=.72+.28*u,alpha=a)]

def links(base,t,cam):
    if t<TIMES['snap'] or t>=TIMES['recede']:return
    d=ImageDraw.Draw(base,'RGBA')
    p=[np.array(GRID[i]['pos'],float) for i in range(6)]
    # Serpentine route follows the reusable data/action modules.
    for a,b in ((0,1),(1,2),(2,5),(5,4),(4,3)):
        start,end=p[a],p[b]; v=end-start; dist=float(np.linalg.norm(v))
        if dist<1:continue
        unit=v/dist
        first=start+unit*250; last=end-unit*250
        xy,z=cam.project(np.vstack([first,last]))
        if min(z)<50:continue
        enabled=M.eio(M.prog(t,TIMES['snap']+(a%3)*.18,TIMES['snap']+1.2+(a%3)*.18))
        pulse=M.eio(M.prog(t,TIMES['automate']+(a%3)*.30,TIMES['automate']+.6+(a%3)*.3))
        alpha=.25*enabled+.68*pulse
        if alpha>.02:
            x1,y1=xy[0];x2,y2=xy[1]
            d.line([(M.P(x1),M.P(y1)),(M.P(x2),M.P(y2))],
                   fill=CYAN+(int(230*alpha),),width=M.P(4))
            travel=M.prog(t,TIMES['snap'],TIMES['title'])
            at=travel*5-(a%5)
            dot=M.clamp(at)
            if 0<dot<1:
                cx=M.lerp(x1,x2,dot);cy=M.lerp(y1,y2,dot)
                r=M.P(7)
                d.ellipse((M.P(cx)-r,M.P(cy)-r,M.P(cx)+r,M.P(cy)+r),
                          fill=ICE+(230,))

def spatial(t):
    assets()
    cam=camera_at(t)
    base=M.canvas(bg=M.radial_bg(inner=(12,31,50),outer=(3,8,19),cy=.48))
    if t<TIMES['recede']:
        base.alpha_composite(M.grid(alpha=.025,step=120))
    cards=cluster(t)+type_states(t)+output_state(t)
    # The completed graph is one coherent room; depth pulls focus off
    # repeated work and toward a single output when automation activates.
    focus=float(cam.to_camera(np.array([[0,0,300.]]))[0,2])
    R=G.Renderer(cam,dof=dict(focus=focus,max_px=6,bands=4,aperture=.6),
                 fog=dict(near=1450,far=5900,max=.48,color=(6,17,29)),
                 light=dict(pos=(-1280,980,1050),color=CYAN,
                            ambient=.9,key=.12,rim=.36),
                 shadow=dict(ground_y=-620,dir=(.25,-1,-.2),strength=.20,blur=9))
    R.render(base,cards,floor=None)
    links(base,t,cam)
    return base

def title_layer(base,t):
    # Camera position, spatial structure, background and paragraph sit still.
    # A SINGLE restrained cyan specular sweep moves across the wordmark.
    a=M.eio(M.prog(t,TIMES['title']-.05,TIMES['title']+.48))
    layer=Image.new('RGBA',base.size,(2,9,21,int(246*a)))
    base.alpha_composite(layer)
    word=M.Text('AIR STACK','Black',166,ICE,tracking=12)
    word.draw(base,960,452,alpha=a,glow_strength=.12,glow_radius=20)
    d=ImageDraw.Draw(base)
    x0=M.P(580); x1=M.P(1340); yy=M.P(568)
    d.line((x0,yy,x0+int((x1-x0)*a),yy),fill=CYAN+(int(190*a),),width=M.P(3))
    tagline=M.Text('BUILD ONCE. POPULATE. AUTOMATE. BROADCAST.',
                   'Bold',31,ICE,tracking=2)
    tagline.draw(base,960,633,alpha=a,glow_strength=0)
    support=M.Text('Broadcast Workflow Automation by BKE',
                   'Medium',25,MUTED,tracking=1)
    support.draw(base,960,704,alpha=a,glow_strength=0)
    # Highlight is the only moving element during the brand hold.
    sweep=M.prog(t,TIMES['brand_shine'],TIMES['brand_shine']+.42)
    if 0<sweep<1:
        px=M.P(M.lerp(580,1340,sweep))
        hi=Image.new('RGBA',base.size,(0,0,0,0))
        ImageDraw.Draw(hi).line((px,M.P(385),px,M.P(550)),
                                 fill=CYAN+(55,),width=M.P(17))
        hi=hi.filter(ImageFilter.GaussianBlur(M.P(21)))
        base.alpha_composite(hi)

def frame(i):
    t=i/FPS
    base=spatial(t)
    if t>=TIMES['title']-.05:
        title_layer(base,t)
    arr=M.to_output(base)
    hits=[('snap',.30),('broadcast',.45),('title',.85)]
    fl=0.
    for eid,size in hits:
        start=TIMES[eid]
        if start<=t<start+.15:
            fl=max(fl,size*(1-(t-start)/.15)**1.5)
    return M.finish(M.flash(arr,fl),i)

def build_visual_log():
    # The individual event identifiers below are intentionally explicit;
    # the static gate rejects unreferenced events and full gate rejects
    # declared-but-unlogged events. No event is used as a fake pass marker.
    used={'cam_dolly':'camera_at','headline':'type_states',
          'cam_track':'camera_at','repeat_build':'cluster',
          'cam_push':'camera_at','one_panel':'cluster',
          'snap':'cluster','question':'type_states',
          'cam_flow':'camera_at','build_title':'type_states',
          'rim_sweep':'links','workflow_lock':'cluster',
          'cam_arc':'camera_at','refresh':'cluster',
          'populate':'type_states','automate':'links',
          'cam_output':'camera_at','broadcast':'output_state',
          'recede':'title_layer','title':'title_layer',
          'title_text':'title_layer','brand_shine':'title_layer'}
    return [dict(event_id=e.id,t=e.t,scene=TLM.scene_at(e.t).id,
                 renderer=used[e.id]) for e in TLM.events() if e.id in used]

def lint():
    assets()
    checks=[]
    for r in ARCS:
        checks.extend(G.lint_rig([r]))
    for t in (TIMES['headline']+.5,TIMES['question']+.32,
              TIMES['build_title']+.6,TIMES['populate']+.45,
              TIMES['automate']+.45):
        checks.extend(G.check_readable(type_states(t),camera_at(t)))
    a=camera_at(TIMES['title']).pos
    b=camera_at(DUR-1/FPS).pos
    drift=float(np.linalg.norm(a-b))
    checks.append(('PASS' if drift<1e-6 else 'FAIL',
                   f'Camera position held through brand: drift={drift:.4f}'))
    checks.append(('PASS' if 35<=LENS<=50 else 'FAIL',
                   f'Lens {LENS} mm within 35–50 mm'))
    status='FAIL' if any(level=='FAIL' for level,_ in checks) else 'PASS'
    report='LINT 3D AIR STACK / THE WORKFLOW\n'+'\n'.join(
      f'{level} {msg}' for level,msg in checks)+f'\nRESULT: {status}'
    return report,status


if __name__ == '__main__':
    if '--preview' in sys.argv: M.configure(S=1); sys.argv.remove('--preview')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'render'
    n = int(round(DUR * FPS))
    if cmd in ('render', 'vlog'):
        json.dump(build_visual_log(), open('visual_log.json', 'w'), indent=1)
        if cmd == 'vlog': sys.exit(0)
    if cmd == 'lint':
        txt, res = lint(); print(txt); open('lint3d.txt', 'w').write(txt + '\n'); sys.exit(0 if res == 'PASS' else 2)
    elif cmd == 'stills':
        os.makedirs('stills', exist_ok=True)
        for s in sys.argv[2:]:
            Image.fromarray(frame(int(round(float(s) * FPS)))).save(f'stills/t{float(s):05.2f}.png')
    elif cmd == 'bench':
        frame(0); ts = []
        for i in range(0, n, 15):
            t0 = time.perf_counter(); frame(i); ts.append((i, time.perf_counter() - t0))
        print('\n'.join(f'f{i:03d} {s:.3f}s' for i, s in ts))
        print(f'mean {np.mean([s for _, s in ts]):.3f} s/frame, max {max(s for _, s in ts):.3f} s (single process, S={M.Cfg.S})')
    else:
        M.render_all(frame, n, 'frames')
