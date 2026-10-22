"""
Eval reliability from our runs: pass@1 vs pass^2 (both attempts solve) per setup, how many
tasks it takes to order two setups correctly from one run each, and silent failures (agent
finished on its own, answer wrong).

    python reliability.py      # text to stdout (reliability.md)
"""
import json, random, statistics as st, sys
from collections import defaultdict
sys.path.insert(0,'.')
import analysis as an
random.seed(0)
rows=an.load(); cells=an.by_cell(rows)
big={k:v for k,v in cells.items() if len(v)>=72}
print("== A. pass@1 vs pass^2 (both attempts solve): do rankings flip? cells with k2 runs")
k2=defaultdict(lambda: defaultdict(list))
for r in rows:
    if r['task_set']!='full-k2': continue
    k=(r['harness'],r['config'],r['concurrency'],r['gpu'])
    by=defaultdict(list)
    for t in r['trials']: by[t['task']].append(t['ok'])
    for task,v in by.items():
        if len(v)==2: k2[k][task].append(v)
res=[]
for k,tasks in k2.items():
    pairs=[p for v in tasks.values() for p in v]
    if len(pairs)<30: continue
    p1=st.mean(x for p in pairs for x in p); p2=st.mean(all(p) for p in pairs); any_=st.mean(any(p) for p in pairs)
    res.append((k,p1,p2,any_,len(pairs)))
for k,p1,p2,a,n in sorted(res,key=lambda x:(x[0][0],-x[1])):
    print(f"  {k[0]:15s} {k[1]:16s} c={k[2]:2d} {k[3]:6s} pass@1 {p1:.2f}  pass^2 {p2:.2f}  pass@2 {a:.2f}  consistency {p2/p1 if p1 else 0:.2f} n={n}")
for h in ('terminus-2','mini-swe-agent'):
    r=[x for x in res if x[0][0]==h]
    import itertools
    flips=sum(1 for a,b in itertools.combinations(r,2) if (a[1]-b[1])*(a[2]-b[2])<0)
    print(f"  {h}: {flips} of {len(r)*(len(r)-1)//2} config pairs swap order between pass@1 and pass^2")

print("\n== B. How many tasks to rank two setups correctly? (bootstrap subsets of tasks, big cells)")
for h in ('terminus-2','mini-swe-agent'):
    ks=[k for k in big if k[0]==h]
    succ={k:an.success(big[k]) for k in ks}
    tasks=sorted(set.intersection(*[set(s) for s in succ.values()]))
    import itertools
    for gap_lo,gap_hi in ((0.03,0.07),(0.08,0.15)):
        prs=[(a,b) for a,b in itertools.combinations(ks,2) if gap_lo<=abs(st.mean(succ[a].values())-st.mean(succ[b].values()))<gap_hi]
        if not prs: continue
        out=[]
        for n in (10,20,36,100):
            ok=0;tot=0
            for a,b in prs:
                true=st.mean(succ[a][t] for t in tasks)>st.mean(succ[b][t] for t in tasks)
                for _ in range(200):
                    ts=[random.choice(tasks) for _ in range(n)]
                    # one trial per task: sample a single outcome per task from its rate
                    sa=sum(random.random()<succ[a][t] for t in ts); sb=sum(random.random()<succ[b][t] for t in ts)
                    tot+=1; ok+= (sa>sb)==true if sa!=sb else 0.5
            out.append(f"{n} tasks: {ok/tot:.0%}")
        print(f"  {h}, true gap {int(gap_lo*100)}-{int(gap_hi*100)} pts ({len(prs)} pairs), one run each, right order: "+", ".join(out))

print("\n== C. Silent failures: agent finished (no time-out) but the answer was wrong")
for h in ('terminus-2','mini-swe-agent'):
    ts=[t for r in rows if r['harness']==h for t in r['trials'] if t.get('steps')]
    fin=[t for t in ts if t.get('exc') is None]
    wrong=[t for t in fin if not t['ok']]; right=[t for t in fin if t['ok']]
    print(f"  {h}: of {len(fin)} trials that ended on their own, {len(wrong)/len(fin):.0%} were wrong; "
          f"median steps wrong {st.median(t['steps'] for t in wrong):.0f} vs right {st.median(t['steps'] for t in right):.0f}; "
          f"median agent time wrong {st.median(t['agent_s'] for t in wrong):.0f}s vs right {st.median(t['agent_s'] for t in right):.0f}s")
