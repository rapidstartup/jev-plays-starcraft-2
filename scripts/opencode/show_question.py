import json, glob, os
path=sorted(glob.glob('runs/2026*/events.jsonl'),key=os.path.getmtime)[-1]
for line in open(path,encoding='utf-8',errors='ignore'):
    try: x=json.loads(line)
    except: continue
    if x.get('event')=='jev' and 'MobileCombat' in x.get('questions',{}):
        q=x['questions']['MobileCombat']
        crit=q.get('criteria',{})
        print('MobileCombat question:')
        print('  instructions chars=',len(q.get('instructions','')))
        print('  num criteria=',len(crit))
        sizes=sorted(((len(v),k) for k,v in crit.items()),reverse=True)
        print('  criteria sizes (desc chars) top10=',[s for s,_ in sizes[:10]])
        for n,k in sizes[:4]:
            print(f'   [{k}] ({n} chars): {crit[k][:160]}')
        # typical
        med=sizes[len(sizes)//2]
        print(f'   median example [{med[1]}] ({med[0]}): {crit[med[1]][:160]}')
        break
# also the strategy q=2 (nq=2) and purpose question
for line in open(path,encoding='utf-8',errors='ignore'):
    try: x=json.loads(line)
    except: continue
    if x.get('event')=='jev' and 'strategy' in x.get('questions',{}) and len(x['questions'])==2:
        print('strategy q2: instr chars=',len(x['questions']['strategy'].get('instructions','')),'criteria=',len(x['questions']['strategy'].get('criteria',{})))
        break
