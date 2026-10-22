"""Score Jev as a policy gate on decisions we already recorded, before running any new conversations.

  JEV_API_KEY=... python scripts/jev_calibrate.py <raw-root> <out.jsonl> [--per-tool 120]   (tau2 venv)

Takes every state-changing action that bank agents proposed on the hidden set (GPT-5, GPT-6 Luna, GPT-5.4 nano, Qwen
BF16/FP8 and the hosted providers' runs) and labels it right or wrong against the scenario's gold actions:
right = the same tool with the same key arguments as a gold action; wrong = anything else. Samples up to N per tool,
balanced between right and wrong, asks Jev "does the policy allow this now?" with the conversation up to that point,
and reports how many wrong actions Jev would block and how many right ones it would wrongly block.
"""
import argparse
import glob
import json
import os
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench.jev_agent import MIN_CONF, RULES, ask_jev  # noqa: E402

KEY_ARGS = {"escalate_to_human": ["reason"], "issue_refund": ["transaction_id", "amount", "reason"],
            "open_dispute": ["transaction_id", "reason"], "freeze_card": ["card_id", "reason"]}


def norm(name, args):
    keep = KEY_ARGS.get(name, sorted(args))
    out = []
    for k in keep:
        v = args.get(k)
        try:
            v = f"{float(v):.2f}"
        except (TypeError, ValueError):
            v = str(v)
        out.append((k, v))
    return name, tuple(out)


def render(msgs, name, args, max_chars=12000):
    lines = []
    for m in msgs:
        if m["role"] == "user":
            lines.append(f"Customer: {m.get('content')}")
        elif m["role"] == "assistant":
            if m.get("content"):
                lines.append(f"Agent: {m['content']}")
            for t in m.get("tool_calls") or []:
                lines.append(f"Agent calls {t['name']}({json.dumps(t['arguments'])})")
        elif m["role"] == "tool":
            lines.append(f"Tool result: {str(m.get('content'))[:1500]}")
    return "\n".join(lines)[-max_chars:] + f"\n\nPROPOSED ACTION: {name}({json.dumps(args)})"


def items(path, run):
    for s in json.load(open(path))["simulations"]:
        ri = s.get("reward_info")
        if not ri:
            continue
        gold = [norm(a["action"]["name"], a["action"]["arguments"]) for a in ri.get("action_checks") or []]
        msgs = s["messages"]
        for i, m in enumerate(msgs):
            if m["role"] != "assistant":
                continue
            for t in m.get("tool_calls") or []:
                if t["name"] in RULES:
                    yield dict(run=run, scenario=s["task_id"], trial=s["trial"], tool=t["name"], arguments=t["arguments"],
                               right=norm(t["name"], t["arguments"]) in gold, state=render(msgs[:i], t["name"], t["arguments"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out")
    ap.add_argument("--per-tool", type=int, default=120)
    ap.add_argument("--tools", nargs="*", default=None)
    a = ap.parse_args()
    paths = [p for p in glob.glob(os.path.join(a.root, "f*/**/test/results.json"), recursive=True)
             if "/guard/" not in p and "/rft/" not in p] + glob.glob(os.path.join(a.root, "prov_hidden/[!_]*/test/results.json"))
    pool = defaultdict(list)
    for p in paths:
        for it in items(p, os.path.relpath(os.path.dirname(os.path.dirname(p)), a.root)):
            pool[(it["tool"], it["right"])].append(it)
    rng = random.Random(0)
    sample = []
    for tool in (a.tools or RULES):
        for right in (False, True):
            xs = pool[(tool, right)]
            rng.shuffle(xs)
            sample += xs[: a.per_tool // 2]
    print({f"{t}/{'right' if r else 'wrong'}": len(v) for (t, r), v in sorted(pool.items())}, "-> sample", len(sample))

    def run(it):
        d = ask_jev(it["state"], it["tool"])
        return dict({k: v for k, v in it.items() if k != "state"}, **d)

    with ThreadPoolExecutor(8) as ex, open(a.out, "w") as f:
        res = list(ex.map(run, sample))
        for r in res:
            f.write(json.dumps(r) + "\n")
    print("\n| action | wrong actions | blocked | right actions | wrongly blocked | Jev errors |\n|---|---|---|---|---|---|")
    for tool in RULES:
        w = [r for r in res if r["tool"] == tool and not r["right"] and r["choice"] != "error"]
        c = [r for r in res if r["tool"] == tool and r["right"] and r["choice"] != "error"]
        blk = lambda r: r["choice"] == "not_allowed" and (r.get("confidence") or 0) >= MIN_CONF  # noqa: E731
        err = sum(r["choice"] == "error" for r in res if r["tool"] == tool)
        print(f"| {tool} | {len(w)} | {sum(map(blk, w))} ({sum(map(blk, w)) / max(len(w), 1):.0%}) | {len(c)} | "
              f"{sum(map(blk, c))} ({sum(map(blk, c)) / max(len(c), 1):.0%}) | {err} |")


if __name__ == "__main__":
    main()
