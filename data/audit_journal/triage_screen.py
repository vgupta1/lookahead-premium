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

import os, sys, csv, json, hashlib, datetime, argparse, urllib.request, collections

MODEL = "claude-opus-4-5-20251101"   # a model change is a methodology change; override with --model
# WHY A DATED SNAPSHOT (VG, 2026-09-17). Unversioned aliases -- claude-opus-5, claude-opus-4-8 --
# float to newer snapshots over time, so a rerun months later need not reproduce today's
# classifications. For a paper about reporting discipline that is not a cost worth paying. A dated
# id is fixed. The likely tradeoff is some judgement quality on marginal records; the plan is to
# take that trade, see how many records the k runs actually split on, and only reach for a stronger
# floating model if the human-review pile is large. Every output row records the model id used, so
# either choice stays attributable.
TEMPERATURE = 0
RUNS = 3                  # k-run majority vote; override with --runs
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

2a. The learned component need NOT predict problem data -- it may be the solver itself. A model that \
learns to produce solutions to an optimization problem (amortized optimization, learned solvers, \
neural combinatorial optimization) satisfies the "learned component" condition, and such papers are \
CANDIDATE. Both conjuncts still apply: a paper proposing a better classical algorithm with nothing \
learned in it (a variance-reduced gradient method, a new interior-point step) is OUT because there \
is no learned component, and simulation of a physical system is OUT because there is no decision \
problem. Judge what the paper takes as its object: a work whose goal is solving an optimization \
problem faster is CANDIDATE; a work that merely uses a solver as machinery for some other goal \
(learning interpretable rules, training a classifier) is not.

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

"Meta Optimal Transport" -- amortized optimization to predict optimal-transport maps from the input \
measures, used to improve the computational time of standard OT solvers.
-> CANDIDATE. Optimal transport is an optimization problem and is the object of the work; the \
learned model is the solver (rule 2a). That nothing is predicted, and that the contribution is \
purely computational, are both irrelevant here.

"Learning Reliable Logical Rules with SATNet" -- decodes SATNet's learned weights into interpretable \
weighted-MaxSAT rules and verifies them.
-> OUT. MaxSAT is machinery; the object of the work is learning and verifying interpretable rules. \
Contrast Meta OT, whose stated goal is solving the optimization problem faster.

Return ONLY a JSON object, no other text:
{"bucket": "CANDIDATE" | "OUT" | "UNCLEAR", "reason": "<one sentence, max 25 words>", \
"confidence": "high" | "medium" | "low"}
"""

PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]


def classify(title, abstract, key, model=MODEL):
    body = json.dumps({
        "model": model, "max_tokens": 300, "temperature": TEMPERATURE, "system": PROMPT,
        "messages": [{"role": "user", "content": f"Title: {title}\n\nAbstract: {abstract[:4000]}"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        txt = json.loads(r.read())["content"][0]["text"].strip()
    return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])


def validate(key, model=MODEL):
    """Control set: 12 papers already in the workshop audit, so all are in scope and the only
    acceptable buckets are CANDIDATE and UNCLEAR. Abstracts are stored verbatim in the JSON (not
    re-parsed from PDFs, which is not reproducible). The four marked difficulty='narrow' carry no
    prediction language at all and are the binding test -- an earlier rule that asked whether a
    parameter is predicted excluded all four."""
    recs = json.load(open(os.path.join(HERE, "triage_control_abstracts.json"),
                          encoding="utf-8"))["records"]
    fails = []
    for r in recs:
        v = classify(r["title"], r["abstract"], key, model)
        ok = v["bucket"] in ("CANDIDATE", "UNCLEAR")
        if not ok:
            fails.append((r, v))
        print(f"  {'PASS' if ok else 'FAIL'}  [{r['difficulty']:8}] "
              f"{r['bibkey']:34} {v['bucket']:9} {v['reason'][:58]}")
    out = [f"Triage control set, {datetime.date.today()}",
           f"model={model} temperature={TEMPERATURE} prompt_hash={PROMPT_HASH}",
           f"{len(recs)-len(fails)}/{len(recs)} passed"]
    for r, v in fails:
        out.append(f"FAIL {r['bibkey']} [{r['difficulty']}] -> {v['bucket']}: {v['reason']}")
    open(os.path.join(HERE, "triage_validation.txt"), "w").write("\n".join(out) + "\n")
    print("\n" + "\n".join(out))
    return not fails


SWEEP_FILE = f"venue_sweep_{DATE}.csv"   # named, not globbed: venue_sweep_keys_*.csv also matches
                                         # a glob and carries no abstracts.

def run(key, model=MODEL, k=RUNS):
    """Classify every record k times and take a majority vote.

    Rationale: a fixed prompt is ~99% bucket-stable run to run (see --stability), so most records
    settle unanimously and need no human attention. The value of k>1 is that it IDENTIFIES the
    records where the judgement is genuinely marginal -- those are the only ones worth a human
    ruling, and the count of them is itself reportable. `agreement` records how many of the k runs
    backed the winning bucket; `buckets_all` keeps the raw votes.
    """
    src = os.path.join(HERE, SWEEP_FILE)
    if not os.path.exists(src):
        sys.exit(f"sweep table not found: {src}\nRun build_venue_sweep.py first.")
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig", newline="")))
    if "abstract" not in rows[0]:
        sys.exit(f"{SWEEP_FILE} has no 'abstract' column -- this looks like the keys file, which\n"
                 "carries no publisher content. Triage needs the full sweep table.")
    today, out = str(datetime.date.today()), []
    for i, r in enumerate(rows, 1):
        if (r["abstract"] or "").lower().lstrip().startswith("the proceedings contain"):
            votes = [{"bucket": "OUT", "reason": "proceedings front matter, not a paper",
                      "confidence": "high"}]    # metadata artifact, not a paper; no need to vote
        else:
            votes = [classify(r["title"], r["abstract"], key, model) for _ in range(k)]
        tally = collections.Counter(v["bucket"] for v in votes)
        top, n_top = tally.most_common(1)[0]
        # A record with no majority (k-way split) is flagged for adjudication, not silently binned.
        needs = "yes" if n_top <= len(votes) / 2 else ""
        pick = next(v for v in votes if v["bucket"] == top)
        out.append(dict(sweep_id=r["sweep_id"], venue=r["venue"], year=r["year"], title=r["title"],
                        bucket=top, agreement=f"{n_top}/{len(votes)}",
                        needs_adjudication=needs,
                        buckets_all=";".join(v["bucket"] for v in votes),
                        reason=pick["reason"], confidence=pick["confidence"],
                        frame_id=r["frame_id"], model_id=model, runs=len(votes),
                        prompt_hash=PROMPT_HASH, run_date=today))
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}")

    p = os.path.join(HERE, f"triage_{DATE}.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print("\n" + str(collections.Counter(o["bucket"] for o in out)))
    print("agreement:", dict(collections.Counter(o["agreement"] for o in out)))

    # In-distribution positive control, free: rows already cited by a seed survey should not be OUT.
    flagged = [o for o in out if o["frame_id"] and o["bucket"] == "OUT"]
    print(f"\nseed-frame rows marked OUT: {len(flagged)} (inspect each)")
    for o in flagged:
        print(f"  {o['sweep_id']} {o['frame_id']} {o['title'][:60]} -- {o['reason'][:50]}")

    # The only rows needing human time: where the k runs did not agree unanimously.
    split = [o for o in out if o["agreement"].split("/")[0] != o["agreement"].split("/")[1]]
    print(f"\nrecords where the {k} runs disagreed -> hand-rule these: {len(split)}")
    for o in split:
        print(f"  {o['sweep_id']} {o['venue']:8}{o['year']} [{o['buckets_all']}] {o['title'][:52]}")
    print("\nwrote", p)


def stability(key, n, model=MODEL):
    """Re-run the CURRENT prompt on a random n records and compare with triage_<DATE>.csv.

    Why this exists: after a prompt revision, 15 of 379 records changed bucket and 329 changed
    their stated rationale. A targeted edit should not move that much, so either the edit
    perturbed every borderline judgement or temperature-0 variation is larger than assumed.
    Those have different consequences -- the second would mean single-run triage is not
    reproducible enough to report, and k-run majority voting becomes necessary. This measures
    it: same prompt, same model, same inputs, twice.
    """
    import random
    prior = {r["sweep_id"]: r for r in
             csv.DictReader(open(os.path.join(HERE, f"triage_{DATE}.csv"),
                                 encoding="utf-8-sig", newline=""))}
    rows = {r["sweep_id"]: r for r in
            csv.DictReader(open(os.path.join(HERE, SWEEP_FILE),
                                encoding="utf-8-sig", newline=""))}
    random.seed(20260917)
    ids = random.sample(sorted(set(prior) & set(rows)), min(n, len(prior)))
    agree_b = agree_r = 0
    flips = []
    for i, s in enumerate(ids, 1):
        v = classify(rows[s]["title"], rows[s]["abstract"], key, model)
        if v["bucket"] == prior[s]["bucket"]:
            agree_b += 1
        else:
            flips.append((s, prior[s]["bucket"], v["bucket"], rows[s]["title"][:60]))
        if v["reason"].strip() == prior[s]["reason"].strip():
            agree_r += 1
        if i % 25 == 0:
            print(f"  {i}/{len(ids)}")
    print(f"\nSame prompt ({PROMPT_HASH}), same model, run twice, n={len(ids)}:")
    print(f"  bucket agreement   : {agree_b}/{len(ids)} ({agree_b/len(ids):.0%})")
    print(f"  identical rationale: {agree_r}/{len(ids)} ({agree_r/len(ids):.0%})")
    if flips:
        print("\n  bucket disagreements:")
        for s, x, y, t in flips:
            print(f"    {s} {x} -> {y}  {t}")
    open(os.path.join(HERE, "triage_stability.txt"), "w").write(
        f"prompt_hash={PROMPT_HASH} model={MODEL} temperature={TEMPERATURE} n={len(ids)}\n"
        f"bucket agreement {agree_b}/{len(ids)}; identical rationale {agree_r}/{len(ids)}\n"
        + "".join(f"{s} {x} -> {y} {t}\n" for s, x, y, t in flips))
    print("\nwrote triage_stability.txt")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--stability", type=int, metavar="N",
                    help="re-run the current prompt on N random records and report agreement")
    ap.add_argument("--model", default=MODEL, help=f"model id (default {MODEL})")
    ap.add_argument("--runs", type=int, default=RUNS,
                    help=f"majority-vote over this many runs (default {RUNS})")
    a = ap.parse_args()
    k = os.environ.get("ANTHROPIC_API_KEY") or sys.exit("set ANTHROPIC_API_KEY")
    if a.stability:
        stability(k, a.stability, a.model)
    elif a.validate:
        sys.exit(0 if validate(k, a.model) else 1)
    elif a.run:
        print(f"model={a.model}  runs={a.runs}  prompt_hash={PROMPT_HASH}\n")
        if not validate(k, a.model):
            sys.exit("control set failed -- fix the prompt before triaging anything")
        run(k, a.model, a.runs)
    else:
        ap.print_help()
