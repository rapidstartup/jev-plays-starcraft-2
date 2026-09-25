import json, sys, os, glob, statistics
runs=sorted(glob.glob('runs/2026*/events.jsonl'),key=os.path.getmtime)
path=runs[-1]
print('run=',os.path.basename(os.path.dirname(path)))
rows=[]
for line in open(path,encoding='utf-8',errors='ignore'):
    try: x=json.loads(line)
    except: continue
    rows.append(x)
jev=[r for r in rows if r.get('event')=='jev']
errs=[r for r in rows if r.get('event') in ('decision_error','soft_decision_failure')]
print('jev asks=',len(jev),' errors=',len(errs))
st=[len(json.dumps(r.get('state',{}))) for r in jev]
qs=[len(json.dumps(r.get('questions',{}))) for r in jev]
print('state chars med/max=',int(statistics.median(st)) if st else 0,max(st) if st else 0)
print('quest chars med/max=',int(statistics.median(qs)) if qs else 0,max(qs) if qs else 0)
slow=sorted([r for r in jev if r.get('latency_ms',0)>5000],key=lambda z:-z['latency_ms'])
print('--- slowest asks ---')
for r in slow[:8]:
    s=r.get('state',{}); q=r.get('questions',{})
    print(f"  lat={r['latency_ms']:6d}ms state={len(json.dumps(s)):5d} quest={len(json.dumps(q)):5d} nq={len(q)} keys={list(q.keys())[:3]}")
    # biggest state fields
    big=sorted(((len(json.dumps(v)),k) for k,v in s.items()),reverse=True)[:4]
    print('      big fields:',[(k,n) for n,k in big])
# decision_error details
de=[r for r in rows if r.get('event')=='decision_error']
print('--- decision_error count=',len(de))
if de: print('  sample:',{k:de[0].get(k) for k in ('error','detail','timeout_count')})
# guide
g=[r for r in rows if r.get('event')=='guide']
print('guide calls=',len(g))
# command outcome
ack=[r for r in rows if r.get('event') in ('commands','ack','applied')]
print('ack/applied events=',len(ack))
