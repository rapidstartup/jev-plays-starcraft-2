import json, glob, os, sys, time
path=sorted(glob.glob('runs/2026*/events.jsonl'),key=os.path.getmtime)[-1]
print('run=',os.path.basename(os.path.dirname(path)))
rows=[]
for line in open(path,encoding='utf-8',errors='ignore'):
    try: x=json.loads(line)
    except: continue
    rows.append(x)
t0=rows[0].get('time') if rows else 0
# game loop from jev/camera/decision events
loops=[r.get('loop') for r in rows if r.get('loop') is not None]
if loops:
    print(f'game loop: first={loops[0]} last={loops[-1]} span={loops[-1]-loops[0]}')
# timeline: game loop vs wall time
print('--- loop progression (every ~10s) ---')
last_t=None
for r in rows:
    t=r.get('time',0); l=r.get('loop')
    if l is None: continue
    if last_t is None or t-last_t>=10:
        ev=r.get('event')
        print(f'  t=+{t-t0:6.0f}s loop={l} event={ev}')
        last_t=t
# recent distinct decisions (are they repeating?)
jev=[r for r in rows if r.get('event')=='jev']
recent=jev[-40:]
choices=[]
for r in recent:
    resp=r.get('response',{})
    for k,v in (resp.get('answers') or {}).items():
        if isinstance(v,dict): choices.append(v.get('choice'))
from collections import Counter
print('--- recent choice distribution (last 40 asks) ---')
for c,n in Counter(choices).most_common(10): print(f'  {c}: {n}')
# result?
rp=os.path.join(os.path.dirname(path),'result.json')
print('result.json exists=',os.path.exists(rp))
