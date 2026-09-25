import asyncio, os, time, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from jev_sc2.jev import Jev

def state(n_ally, n_enemy, squad):
    return {
        "objective": "Destroy the Logistics Headquarters. Raynor must survive.",
        "loop": 1200,
        "resources": {"minerals": 150, "vespene": 0, "food_used": 12, "food_cap": 20},
        "visible_entities": (
            [{"tag": f"m{i}", "type": "Marine", "alliance": "Ally", "position": [80.0+i, 50.0+(i%5)]} for i in range(n_ally)]
            + [{"tag": f"e{i}", "type": "Queen", "alliance": "Enemy", "position": [95.0+i, 55.0+(i%4)]} for i in range(n_enemy)]
            + [{"tag": "hq", "type": "LogisticsHeadquarters", "alliance": "Enemy", "position": [120.0, 60.0]}]
        ),
        "squad": [{"tag": 100+i, "type": "Marine", "position": [80.0+i, 50.0], "health_fraction": 0.8, "build_progress": 1.0} for i in range(squad)],
    }

Q = {"q1": {"type":"choice","instructions":"Choose the best action.","criteria":{"attack_move":"Attack-move toward the enemy base.","hold":"Hold position.","retreat":"Retreat away."}}}

async def main():
    jev = Jev(lambda *a, **k: None, "scaling", max_calls=None)
    for (a, e, s) in [(10,10,4),(20,20,6),(40,30,8),(60,45,10),(80,60,12),(120,80,16)]:
        t0 = time.perf_counter()
        try:
            ans = await asyncio.wait_for(jev.ask(state(a,e,s), Q), timeout=120)
            dt = (time.perf_counter()-t0)*1000
            ch = [v.get("choice") for v in ans.values() if isinstance(v,dict)]
            print(f"ally={a:3d} enemy={e:3d} squad={s:2d}  latency_ms={dt:8.0f}  choice={ch}")
        except Exception as ex:
            dt = (time.perf_counter()-t0)*1000
            print(f"ally={a:3d} enemy={e:3d} squad={s:2d}  latency_ms={dt:8.0f}  ERROR {type(ex).__name__}")

asyncio.run(main())
