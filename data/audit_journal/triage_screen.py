#!/usr/bin/env python3
"""
triage_screen.py -- stage-1 topic triage for the journal-version literature audit.

This is an LLM classifier with a FIXED prompt, not a keyword match. The criterion it applies is an
interpretive judgement, and such judgements are reproducible only if the prompt, the model and the
per-paper rationale are recorded. That is the point of this file: the judgement lives in PROMPT
below, under version control.

It decides which PDFs to chase. It does NOT decide inclusion -- Gates A and B
(search_protocol.md 2.7) and the four inclusion rules all require full text.

    export ANTHROPIC_API_KEY=...
    python3 triage_screen.py --validate     # control set; always run this first
    python3 triage_screen.py --run          # triage venue_sweep_<DATE>.csv

Outputs triage_<DATE>.csv and triage_validation.txt. Needs network, so it does not run in the
Cowork sandbox.
"""

import os, sys, csv, json, glob, hashlib, datetime, argparse, urllib.request, collections

MODEL = "claude-sonnet-4-5-20250929"   # pinned: a model change is a methodology change
TEMPERATURE = 0
DATE = "2026-09-16"
HERE = os.path.dirname(os.path.abspath(__file__))

PROMPT = """You are screening papers for a literature audit of *contextual optimization* -- settings \
where an optimization problem must be solved but some of its parameters are not known and are \
predicted from context (also called decision-focused learning, predict-then-optimize, \
smart predict-then-optimize, integrated learning and optimization).

You are performing TOPIC TRIAGE ONLY: deciding whether this paper is worth obtaining the full text \
of. You are NOT deciding whether it belongs in the audit.

Classify into exactly one bucket:

CANDIDATE -- there is an optimization or decision problem that is the OBJECT of the work (routing, \
scheduling, matching, shortest path, knapsack, portfolio, inventory, assignment, ranking, an LP or \
MIP, a planning or control problem), AND a learned or predictive component appears in the same \
pipeline.

OUT -- either (a) there is no decision or optimization problem at all (generative modelling, \
representation learning, forecasting with no downstream decision, dataset or benchmark papers), or \
(b) the only "optimization" is machinery for training or compressing the model itself \
(hyperparameter optimization, neural architecture search, pruning, distillation, training dynamics), \
or (c) the work is numerical simulation or solving of physical systems (PDE solvers, differentiable \
physics) with no decision problem.

UNCLEAR -- you cannot tell from the title and abstract.

CRITICAL RULES -- these encode failures observed in testing:

1. DO NOT ask whether anything is predicted, estimated, or uncertain. Many in-scope papers describe \
only their METHOD ("we differentiate through a combinatorial solver") and never mention prediction \
in the abstract, because the setting appears only in their experiments. Excluding on this basis \
wrongly dropped 4 of 12 known in-scope papers in testing.

2. DO NOT exclude a paper because it reads like solver, layer, or proxy work. "Differentiating \
through a solver", "optimization as a layer", "embedding discrete solvers", "combinatorial building \
blocks in neural networks" are all CANDIDATE. Whether such a paper is genuinely in scope is decided \
later, from the full text.

3. When torn between CANDIDATE and OUT, choose CANDIDATE. A wrong OUT is invisible later; a wrong \
CANDIDATE costs one PDF.

4. UNCLEAR is for genuine ambiguity, not mild doubt. It is treated as CANDIDATE downstream.

WORKED EXAMPLES

"Learning with Differentiable Perturbed Optimizers" -- pipelines rely on optimization procedures to \
make discrete decisions (sorting, nearest neighbors, shortest paths); we transform optimizers into \
differentiable operations.
-> CANDIDATE. Shortest paths and ranking are decision problems and are the object of the work; a \
learned model sits in the same pipeline. The abstract never says anything is predicted -- rule 1 \
says that is irrelevant.

"Nonsmooth Implicit Differentiation" -- derivative of the fixed point of a contraction map, with \
applications to hyperparameter optimization, meta-learning, data poisoning.
-> OUT. Every named application is model-training machinery; no external decision problem.

"Learning Neural PDE Solvers with Parameter-Guided Channel Attention"
-> OUT. Numerical simulation of a physical system.

"Addressing Negative Transfer in Diffusion Models"
-> OUT. Generative modelling; no decision problem as the object.

"DISTRICTNET: Decision-aware learning for geographical districting"
-> CANDIDATE. Districting is a combinatorial decision problem and the object of the work.

Return ONLY a JSON object, no other text:
{"bucket": "CANDIDATE" | "OUT" | "UNCLEAR", "reason": "<one sentence, max 25 words>", \
"confidence": "high" | "medium" | "low"}
"""

PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]


def classify(title, abstract, key):
    body = json.dumps({
        "model": MODEL, "max_tokens": 300, "temperature": TEMPERATURE, "system": PROMPT,
        "messages": [{"role": "user", "content": f"Title: {title}\n\nAbstract: {abstract[:4000]}"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        txt = json.loads(r.read())["content"][0]["text"].strip()
    return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])


def validate(key):
    """Control set: 12 papers already in the workshop audit, so all are in scope and the only
    acceptable buckets are CANDIDATE and UNCLEAR. Abstracts are stored verbatim in the JSON (not
    re-parsed from PDFs, which is not reproducible). The four marked difficulty='narrow' carry no
    prediction language at all and are the binding test -- an earlier rule that asked whether a
    parameter is predicted excluded all four."""
    recs = json.load(open(os.path.join(HERE, "triage_control_abstracts.json"),
                          encoding="utf-8"))["records"]
    fails = []
    for r in recs:
        v = classify(r["title"], r["abstract"], key)
        ok = v["bucket"] in ("CANDIDATE", "UNCLEAR")
        if not ok:
            fails.append((r, v))
        print(f"  {'PASS' if ok else 'FAIL'}  [{r['difficulty']:8}] "
              f"{r['bibkey']:34} {v['bucket']:9} {v['reason'][:58]}")
    out = [f"Triage control set, {datetime.date.today()}",
           f"model={MODEL} temperature={TEMPERATURE} prompt_hash={PROMPT_HASH}",
           f"{len(recs)-len(fails)}/{len(recs)} passed"]
    for r, v in fails:
        out.append(f"FAIL {r['bibkey']} [{r['difficulty']}] -> {v['bucket']}: {v['reason']}")
    open(os.path.join(HERE, "triage_validation.txt"), "w").write("\n".join(out) + "\n")
    print("\n" + "\n".join(out))
    return not fails


def run(key):
    src = sorted(glob.glob(os.path.join(HERE, "venue_sweep_*.csv")))[-1]
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig", newline="")))
    today, out = str(datetime.date.today()), []
    for i, r in enumerate(rows, 1):
        if (r["abstract"] or "").lower().lstrip().startswith("the proceedings contain"):
            v = {"bucket": "OUT", "reason": "proceedings front matter, not a paper",
                 "confidence": "high"}          # metadata artifact, not a paper
        else:
            v = classify(r["title"], r["abstract"], key)
        out.append(dict(sweep_id=r["sweep_id"], venue=r["venue"], year=r["year"], title=r["title"],
                        bucket=v["bucket"], reason=v["reason"], confidence=v["confidence"],
                        frame_id=r["frame_id"], model_id=MODEL, prompt_hash=PROMPT_HASH,
                        run_date=today))
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}")

    p = os.path.join(HERE, f"triage_{DATE}.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print("\n" + str(collections.Counter(o["bucket"] for o in out)))

    # In-distribution positive control, free: rows already cited by a seed survey should not be OUT.
    flagged = [o for o in out if o["frame_id"] and o["bucket"] == "OUT"]
    print(f"\nseed-frame rows marked OUT: {len(flagged)} (inspect each)")
    for o in flagged:
        print(f"  {o['sweep_id']} {o['frame_id']} {o['title'][:60]} -- {o['reason'][:50]}")

    # Rows to hand-check: plausible errors, not a uniform sample (see search_protocol.md).
    check = [o for o in out if o["bucket"] == "OUT"
             and (o["confidence"] != "high" or o["venue"] in ("OR", "MS", "MSOM", "IJOC"))]
    print(f"\nOUT rows worth hand-checking (low confidence or OR-side venue): {len(check)}")
    print("wrote", p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    k = os.environ.get("ANTHROPIC_API_KEY") or sys.exit("set ANTHROPIC_API_KEY")
    if a.validate:
        sys.exit(0 if validate(k) else 1)
    elif a.run:
        if not validate(k):
            sys.exit("control set failed -- fix the prompt before triaging anything")
        run(k)
    else:
        ap.print_help()
