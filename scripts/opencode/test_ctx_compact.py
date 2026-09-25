import json, glob, os, sys, statistics
sys.path.insert(0,'.')
from jev_sc2.jev import compact_model_state, compact_questions

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
            desc=int(desc*0.75)
            questions=compact_questions(questions,max_desc_chars=desc)
        else:
            state=compact_model_state(state,budget_chars=max(700,len(json.dumps(state))//2))
    return state,questions

before=[]; after=[]; keys_ok=True
for s,q in rows:
    before.append(len(json.dumps([s,q])))
    cs,cq=pipeline(s,q)
    after.append(len(json.dumps([cs,cq])))
    # every original option key must survive
    for name,qq in q.items():
        if isinstance(qq,dict) and isinstance(qq.get('criteria'),dict):
            got=cq.get(name,{}).get('criteria',{})
            if set(qq['criteria'].keys())!=set(got.keys()):
                keys_ok=False
print('n=',len(rows))
print('BEFORE total(state+questions) med/max=',int(statistics.median(before)),max(before))
print('AFTER  total(state+questions) med/max=',int(statistics.median(after)),max(after))
print('all option keys preserved=',keys_ok)
