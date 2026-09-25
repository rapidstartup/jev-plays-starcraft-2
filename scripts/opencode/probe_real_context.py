import json, glob, os, sys, time, asyncio, statistics
sys.path.insert(0,'.')
from jev_sc2.jev import Jev, compact_model_state, compact_questions

path=sorted(glob.glob('runs/2026*/events.jsonl'),key=os.path.getmtime)[-1]
rows=[]
for line in open(path,encoding='utf-8',errors='ignore'):
    try: x=json.loads(line)
    except: continue
    if x.get('event')=='jev' and x.get('questions'):
        rows.append((x['state'],x['questions']))

def pipeline(state,questions,total_budget=3000):
    state=compact_model_state(state)
    desc=110
    questions=compact_questions(questions,max_desc_chars=desc)
    def ctx(): return len(json.dumps([state,questions]))
    g=0
    while ctx()>total_budget and g<30:
        g+=1
        if desc>45:
            desc=int(desc*0.75); questions=compact_questions(questions,max_desc_chars=desc)
        else:
            state=compact_model_state(state,budget_chars=max(700,len(json.dumps(state))//2))
    return state,questions

# dedupe by total size, pick a spread of representative asks
picked={}
for s,q in rows:
    cs,cq=pipeline(s,q)
    key=round(len(json.dumps([cs,cq]))/200)
    if key not in picked: picked[key]=(cs,cq)
samples=list(picked.values())[:10]

async def main():
    jev=Jev(lambda *a,**k:None,'probe',max_calls=None)
    lats=[]
    for cs,cq in samples:
        total=len(json.dumps([cs,cq]))
        t0=time.perf_counter()
        try:
            ans=await asyncio.wait_for(jev.ask(cs,cq),timeout=90)
            dt=(time.perf_counter()-t0)*1000
            print(f"  total={total:5d}  latency_ms={dt:7.0f}")
            lats.append(dt)
        except Exception as e:
            dt=(time.perf_counter()-t0)*1000
            print(f"  total={total:5d}  latency_ms={dt:7.0f}  ERR {type(e).__name__}")
    if lats:
        print(f"n={len(lats)} med={statistics.median(lats):.0f} max={max(lats):.0f} p90={sorted(lats)[int(.9*len(lats))-1]:.0f}")
asyncio.run(main())
