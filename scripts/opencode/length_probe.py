import asyncio, os, time, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from jev_sc2.jev import Jev

Q = {"q1": {"type":"choice","instructions":"Choose the best action.","criteria":{"attack_move":"Attack-move toward the enemy base.","hold":"Hold position.","retreat":"Retreat away."}}}

def compact(n_units):
    # Intended SystemOne style: a short situation summary, not a full entity dump.
    summary = f"A marine squad of {n_units} units advances toward the enemy base. Light enemy resistance. Choose the next action."
    return {"objective": "Destroy enemy HQ. Keep Raynor alive.", "situation": summary,
            "own_units": n_units, "enemy_units": "light", "loop": 1200}

def dump(n):
    ents = [{"tag": f"u{i}", "type": "Marine", "alliance": "Ally", "position": [80.0+i, 50.0], "health": 0.8, "build": 1.0} for i in range(n)]
    return {"objective": "Destroy enemy HQ. Keep Raynor alive.", "loop": 1200,
            "visible_entities": ents + [{"tag":"hq","type":"HQ","alliance":"Enemy","position":[120.0,60.0]}]}

async def main():
    jev = Jev(lambda *a, **k: None, "lenprobe", max_calls=None)
    print("--- COMPACT summaries (SystemOne-style) ---")
    for n in (4, 8, 16, 32):
        st = compact(n)
        ch = len(json.dumps(st))
        t0=time.perf_counter()
        ans=await asyncio.wait_for(jev.ask(st,Q),timeout=120)
        dt=(time.perf_counter()-t0)*1000
        print(f"compact units={n:3d} chars={ch:5d} latency_ms={dt:7.0f}")
    print("--- FULL entity dumps ---")
    for n in (8, 16, 32, 64):
        st = dump(n)
        ch = len(json.dumps(st))
        t0=time.perf_counter()
        ans=await asyncio.wait_for(jev.ask(st,Q),timeout=120)
        dt=(time.perf_counter()-t0)*1000
        print(f"dump    units={n:3d} chars={ch:5d} latency_ms={dt:7.0f}")

asyncio.run(main())
