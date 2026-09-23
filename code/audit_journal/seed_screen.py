#!/usr/bin/env python3
"""
seed_screen.py -- coarse screen of the seed-survey references (search_protocol.md 2.6, step 1).

The seed frame is the reference lists of the two seed surveys. Reference lists carry no abstracts,
so this screen sees only the printed reference string. It sorts each cited WORK into

    CANDIDATE   plausibly relevant; goes to full text
    BORDERLINE  cannot be ruled background with confidence; VG rules
    BACKGROUND  plainly background (textbooks, general ML methods, software, unrelated fields)

and nothing it decides is terminal: every BACKGROUND and BORDERLINE record, and every record on
which the runs disagree, goes to VG for review (seed_screen_review_<DATE>.csv). The number reported
is VG's count of false exclusions over the WHOLE excluded pile -- a census, not a sample.

It mirrors triage_screen.py: a fixed prompt (the prompt IS the method), the same pinned model,
temperature 0, k runs with a majority vote, and per-record reason + prompt hash + model id. The
prompt is different because the input is different (a reference string, not an abstract) and so is
the question (background vs not, rather than on-topic vs off-topic among venue papers).

UNIT. seed_frame_2026-09-21.csv has 313 bibliography entries = 305 works; rows with `dup_of` set
are second copies of a work and inherit the canonical row's label (the model sees ALL printed
strings for a work at once). The two surveys' entries for each other (SF0185, SF0243) are labelled
SEED structurally, not by the model. So the model classifies 303 works.

    export ANTHROPIC_API_KEY=...
    python3 seed_screen.py --dry-run      # no API calls: counts, and the prompt for one record
    python3 seed_screen.py --validate     # control set only (26 calls); must pass
    python3 seed_screen.py --run          # control set, then 303 works x 3 runs (~935 calls)
    python3 seed_screen.py --run          # again after any interruption: resumes from the cache
    python3 seed_screen.py --run --fresh  # ignore the cache and re-ask every record

RESUMABLE. Each vote is appended to seed_screen_cache_<DATE>.jsonl the moment it returns, keyed by
(frame_id, run index, prompt_hash, model). A dropped connection, a laptop sleeping or a Ctrl-C
therefore costs one call, not the whole run -- rerun the same command. A vote is reused only if the
prompt hash and model still match, so editing the prompt invalidates the cache by construction.

OUTPUTS
    seed_screen_cache_<DATE>.jsonl   every vote as it is returned; the run RESUMES from this file
    seed_screen_<DATE>.csv           one row per frame entry (313), machine labels
    seed_screen_review_<DATE>.csv    the rows VG reviews, with blank vg_ruling / vg_note columns
    seed_screen_validation.txt       control-set result
"""

import os, sys, csv, json, time, socket, hashlib, datetime, argparse, urllib.request, urllib.error, collections
import http.client

MODEL = "claude-opus-4-5-20251101"   # same pinned snapshot as triage_screen.py; a model change is a
                                     # methodology change
TEMPERATURE = 0
RUNS = 3
DATE = "2026-09-22"          # names the outputs; the frame it reads is dated separately
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "data", "audit_journal"))
FRAME = "seed_frame_2026-09-21.csv"
SEED_SELF = {"SF0185": "the JAIR seed survey itself (arXiv version, cited by EJOR)",
             "SF0243": "the EJOR seed survey itself (cited by JAIR)"}

PROMPT = """You are helping screen the reference lists of two survey papers for a literature audit.

THE AUDIT. It studies how papers on *contextual optimization* evaluate their methods. Contextual \
optimization covers any setting where a decision or optimization problem depends on uncertain \
quantities that are predicted, estimated or learned from data or side information: decision-focused \
learning, predict-then-optimize, smart predict-then-optimize, end-to-end or integrated learning and \
optimization, task-based learning, prescriptive analytics, data-driven or contextual stochastic and \
robust optimization, feature-based newsvendor and inventory, and applications of any of these. It \
also covers the methodological machinery this literature builds on: differentiating through \
optimization problems or combinatorial solvers, optimization layers, surrogate losses for decisions.

YOUR TASK. You see one cited work, given as the reference string(s) printed in the survey's \
bibliography -- authors, year, title, venue. There is no abstract. You may use what you know about \
the work if you recognize it. Decide whether it is PLAINLY BACKGROUND -- cited for context, and \
certainly not a paper that proposes, analyses, benchmarks or applies methods in the area above. \
This is a coarse screen. Everything not plainly background will later be read in full, where the \
fine judgements are made. You are NOT deciding whether the work is in scope.

Classify into exactly one bucket:

BACKGROUND -- the work is plainly one of:
  (a) a textbook, monograph, handbook or encyclopedic survey of a GENERAL field (convex optimization, \
linear programming, stochastic programming, robust optimization, graph theory, statistical learning, \
constraint programming, variational analysis);
  (b) a general machine-learning method, architecture or training technique with no decision problem \
as its object (optimizers such as Adam, activation functions, residual networks, variational \
autoencoders, knowledge distillation, adversarial examples, noise-contrastive estimation, \
representation learning, meta-learning);
  (c) a general statistical or estimation method with no downstream decision (kernel methods, \
nonparametric regression, random forests or treatment-effect estimation, information theory);
  (d) general-purpose software, solver manuals, documentation or datasets (PyTorch, Gurobi, \
OR-tools, CVX, PyTorch Lightning, a map editor, a dataset release);
  (e) a classical optimization algorithm or result with nothing learned or predicted in it \
(shortest-path algorithms, operator splitting schemes, knapsack hardness);
  (f) work in an unrelated field (wireless communications, law, computer vision or NLP with no \
decision problem, interpretability in general).

CANDIDATE -- the work plausibly proposes, analyses, benchmarks, surveys or applies methods in the \
area above, or builds the machinery it relies on.

BORDERLINE -- neither of the above is clear. Typical cases: data-driven decision-making WITHOUT \
covariates or side information (distributionally robust optimization from samples alone); inverse \
optimization or learning an optimization model from observed decisions; decision-aware or \
model-based reinforcement learning; learned optimization solvers or optimization proxies; \
differentiable relaxations of discrete operations (sorting, ranking, top-k, submodular maximization) \
whose use in decision problems is unclear; a title you do not recognize and cannot place.

CRITICAL RULES

1. The burden is on EXCLUSION. BACKGROUND requires that any expert in the area would agree without \
hesitation. If you hesitate at all, the answer is BORDERLINE or CANDIDATE. A wrong BACKGROUND can \
lose a relevant paper; a wrong CANDIDATE costs one PDF.

2. Do NOT exclude a work because it reads like solver, layer or machinery work. "Learning with \
algorithmic supervision via continuous relaxations", "Differentiable top-k with optimal transport", \
"DOGE-Train: discrete optimization on GPU with end-to-end training" are all CANDIDATE: titles like \
these never mention prediction, yet such papers often run experiments on decision problems with \
learned inputs. Titles in this literature describe the \
METHOD and leave the setting to the experiments.

3. Do NOT exclude a work because its title lacks keywords such as "decision-focused" or \
"predict-then-optimize". Judge what the work is, not its vocabulary.

4. A survey, tutorial or library of THIS area (decision-focused learning, predict-then-optimize, \
contextual or prescriptive optimization, end-to-end constrained optimization learning) is \
CANDIDATE, not background -- such works often contain benchmarks. Only surveys and textbooks of \
general fields fall under (a).

5. A general-purpose library or solver is BACKGROUND under (d); a library built for this area \
(for example one for end-to-end predict-then-optimize, or for differentiable optimization) is \
CANDIDATE.

6. An application paper counts if it makes decisions from predictions (pricing from demand \
forecasts, ship inspection from risk predictions, energy scheduling from price forecasts). An \
application with prediction but no decision, or a decision problem with nothing predicted or \
learned, is BACKGROUND only if that is plain; otherwise BORDERLINE.

WORKED EXAMPLES

"Srivastava et al. (2014). Dropout: A simple way to prevent neural networks from overfitting. JMLR."
-> BACKGROUND (b). A regularization technique for training networks; no decision problem.

"Nocedal & Wright (2006). Numerical Optimization. Springer."
-> BACKGROUND (a). General textbook.

"Breiman (2001). Random forests. Machine Learning."
-> BACKGROUND (c). An estimation method; any decision use lies elsewhere.

"Tang & Khalil (2024). CaVE: A cone-aligned approach for fast predict-then-optimize with binary \
linear programs. CPAIOR."
-> CANDIDATE. A predict-then-optimize training method; core of the area.

"Xie et al. (2020). Differentiable top-k with optimal transport. NeurIPS."
-> CANDIDATE (rule 2). Differentiable machinery for a discrete selection problem; the title does not \
say whether anything is predicted, and that is irrelevant here.

"Mohajerin Esfahani & Kuhn (2018). Data-driven distributionally robust optimization using the \
Wasserstein metric. Mathematical Programming."
-> BORDERLINE. Data-driven decisions, but without covariates; whether it matters is a full-text call.

"Kool, van Hoof & Welling (2019). Attention, learn to solve routing problems! ICLR."
-> BORDERLINE. A learned solver; nothing obviously predicted, but the object is a decision problem.

"Shannon (1948). A mathematical theory of communication. Bell System Technical Journal."
-> BACKGROUND (f). Unrelated field.

THE REASON. Write one sentence saying what the work is and why it falls in its bucket. For \
BACKGROUND, name the category letter. A human reviewer reads only this sentence, so make it specific.

Return ONLY a JSON object, no other text:
{"bucket": "CANDIDATE" | "BORDERLINE" | "BACKGROUND", "reason": "<one sentence, max 30 words>", \
"confidence": "high" | "medium" | "low"}
"""

PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]

# Control set, in-distribution: frame works whose answer is known. Positives are papers read in
# full for the workshop audit, or the known-noiseless lineage it excluded only at full text -- any
# of them ruled BACKGROUND means the prompt loses papers we know belong. Negatives are works no
# reader would keep; a prompt that cannot exclude them is useless. These works are also classified
# in the main run like every other record; the control is a gate, not a separate sample.
CONTROL_POS = ["SF0026", "SF0281", "SF0206", "SF0245", "SF0028", "SF0089", "SF0082", "SF0252",
               "SF0293", "SF0197", "SF0181", "SF0184", "SF0286", "SF0130", "SF0171", "SF0270",
               "SF0097", "SF0086", "SF0087", "SF0090"]
# Negatives are deliberately works the prompt does NOT name (it names PyTorch, Gurobi, Adam, residual
# networks and shortest-path algorithms as category examples, so those would pass trivially).
CONTROL_NEG = ["SF0017", "SF0065", "SF0296", "SF0145", "SF0163", "SF0199"]


def check_control_disjoint(works):
    """The control set must not appear in the prompt, or passing it proves nothing. Checked by
    first-author surname AND the first four title words, so a shared surname alone does not trip it."""
    low = " ".join(PROMPT.lower().split())
    for fid in CONTROL_POS + CONTROL_NEG:
        r = works[fid][0]
        frag = " ".join(r["title"].lower().split()[:4])
        assert not (frag in low and r["first_author"].split()[0].lower() in low), \
            f"control record {fid} ({r['title'][:40]}) appears in the prompt"


def load_works():
    rows = list(csv.DictReader(open(os.path.join(DATA, FRAME), encoding="utf-8")))
    assert len(rows) == 313, len(rows)
    works = collections.OrderedDict()
    for r in rows:
        works.setdefault(r["dup_of"] or r["frame_id"], []).append(r)
    assert len(works) == 305, len(works)
    check_control_disjoint(works)
    return rows, works


def user_message(members):
    lines = []
    for m in members:
        src = "+".join(s for s, f in (("JAIR", m["in_jair"]), ("EJOR", m["in_sadana"])) if f)
        lines.append(f"[{src}] {' '.join(m['full_entry'].split())[:1200]}")
    head = ("Reference string as printed:" if len(lines) == 1 else
            f"The same work appears as {len(lines)} reference strings:")
    return head + "\n" + "\n".join(lines)


def classify(msg, key, model=MODEL):
    body = json.dumps({"model": model, "max_tokens": 300, "temperature": TEMPERATURE,
                       "system": PROMPT, "messages": [{"role": "user", "content": msg}]}).encode()
    for attempt in range(6):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body,
                headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                txt = json.loads(r.read())["content"][0]["text"].strip()
            v = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
            assert v["bucket"] in ("CANDIDATE", "BORDERLINE", "BACKGROUND"), v
            return v
        except urllib.error.HTTPError as e:
            if e.code in (408, 409, 429, 500, 502, 503, 504, 529) and attempt < 5:
                time.sleep(2 ** attempt * 5); continue
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError,
                http.client.HTTPException, OSError) as e:
            # transport failure: a dropped connection, DNS, or a stalled socket. These are the
            # failures that actually happen on a laptop over an hour-long run.
            if attempt < 5:
                print(f"    transport error ({type(e).__name__}); retry in "
                      f"{2 ** attempt * 5}s"); time.sleep(2 ** attempt * 5); continue
            raise
        except (json.JSONDecodeError, AssertionError, KeyError):
            if attempt < 2:
                continue            # malformed reply: ask again, same input
            raise


CACHE = f"seed_screen_cache_{DATE}.jsonl"


def load_cache(model, fresh=False):
    """Votes already obtained, as {(frame_id, run_index): vote}. Only votes cast under the CURRENT
    prompt hash and model are reused; anything else is ignored, so a prompt edit cannot silently
    mix two specifications in one output."""
    p = os.path.join(DATA, CACHE)
    if fresh or not os.path.exists(p):
        return {}
    out = {}
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue            # truncated final line from a hard kill; drop it
        if r.get("prompt_hash") == PROMPT_HASH and r.get("model") == model:
            out[(r["frame_id"], r["run"])] = r["vote"]
    return out


def cache_put(fid, run_i, vote, model):
    with open(os.path.join(DATA, CACHE), "a", encoding="utf-8") as f:
        f.write(json.dumps({"frame_id": fid, "run": run_i, "prompt_hash": PROMPT_HASH,
                            "model": model, "at": datetime.datetime.now().isoformat(timespec="seconds"),
                            "vote": vote}) + "\n")
        f.flush(); os.fsync(f.fileno())


def validate(key, works, model=MODEL):
    fails, lines = [], []
    for fid, want in [(f, "pos") for f in CONTROL_POS] + [(f, "neg") for f in CONTROL_NEG]:
        v = classify(user_message(works[fid]), key, model)
        ok = (v["bucket"] != "BACKGROUND") if want == "pos" else (v["bucket"] == "BACKGROUND")
        if not ok:
            fails.append((fid, want, v))
        t = works[fid][0]["title"][:55]
        lines.append(f"  {'PASS' if ok else 'FAIL'} [{want}] {fid} {v['bucket']:10} {t}")
        print(lines[-1])
    n = len(CONTROL_POS) + len(CONTROL_NEG)
    out = [f"Seed-screen control set, {datetime.date.today()}",
           f"model={model} temperature={TEMPERATURE} prompt_hash={PROMPT_HASH}",
           f"{n-len(fails)}/{n} passed ({len(CONTROL_POS)} known-relevant must not be BACKGROUND; "
           f"{len(CONTROL_NEG)} obvious background must be BACKGROUND)", ""] + lines
    for fid, want, v in fails:
        out.append(f"FAIL {fid} [{want}] -> {v['bucket']}: {v['reason']}")
    open(os.path.join(DATA, "seed_screen_validation.txt"), "w").write("\n".join(out) + "\n")
    print("\n" + "\n".join(out[:3]))
    return not fails


def run(key, rows, works, model=MODEL, k=RUNS, fresh=False):
    today, lab = str(datetime.date.today()), {}
    todo = [c for c in works if c not in SEED_SELF]
    assert len(todo) == 303, len(todo)
    cache = load_cache(model, fresh)
    have = sum(1 for c in todo for j in range(k) if (c, j) in cache)
    print(f"cached votes reused: {have} of {len(todo)*k}"
          + ("  (--fresh: cache ignored)" if fresh else ""))
    for i, c in enumerate(todo, 1):
        votes = []
        for j in range(k):
            v = cache.get((c, j))
            if v is None:
                v = classify(user_message(works[c]), key, model)
                cache_put(c, j, v, model)
            votes.append(v)
        tally = collections.Counter(v["bucket"] for v in votes)
        top, n_top = tally.most_common(1)[0]
        if n_top <= k / 2:          # no majority: never silently binned
            top = "BORDERLINE"
        pick = next((v for v in votes if v["bucket"] == top), votes[0])
        lab[c] = dict(bucket=top, agreement=f"{n_top}/{k}",
                      buckets_all=";".join(v["bucket"] for v in votes),
                      reason=pick["reason"], confidence=pick.get("confidence", ""), method="llm")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
    for c, why in SEED_SELF.items():
        lab[c] = dict(bucket="SEED", agreement="", buckets_all="", reason=why, confidence="",
                      method="structural")

    out = []
    for r in rows:
        c = r["dup_of"] or r["frame_id"]
        L = lab[c]
        out.append(dict(frame_id=r["frame_id"], canonical_id=c,
                        method=L["method"] if c == r["frame_id"] else "inherited",
                        bucket=L["bucket"], agreement=L["agreement"], buckets_all=L["buckets_all"],
                        reason=L["reason"], confidence=L["confidence"], title=r["title"],
                        year=r["year"], model_id=model if L["method"] == "llm" else "",
                        runs=k if L["method"] == "llm" else "",
                        prompt_hash=PROMPT_HASH if L["method"] == "llm" else "", run_date=today))
    p = os.path.join(DATA, f"seed_screen_{DATE}.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)

    # ---- review sheet: one row per WORK needing VG's ruling
    def unanimous(L): return L["agreement"] and L["agreement"].split("/")[0] == L["agreement"].split("/")[1]
    rev = []
    for c in todo:
        L = lab[c]
        if L["bucket"] in ("BACKGROUND", "BORDERLINE") or not unanimous(L):
            m = works[c]
            src = sorted({s for x in m for s, f in (("JAIR", x["in_jair"]), ("EJOR", x["in_sadana"])) if f})
            rev.append(dict(frame_id=c, also=";".join(x["frame_id"] for x in m[1:]),
                            source="both" if len(src) == 2 else src[0], year=m[0]["year"],
                            machine_bucket=L["bucket"], votes=L["buckets_all"], reason=L["reason"],
                            reference=" ".join(m[0]["full_entry"].split()),
                            vg_ruling="", vg_note=""))
    order = {"BORDERLINE": 0, "CANDIDATE": 1, "BACKGROUND": 2}
    rev.sort(key=lambda r: (order[r["machine_bucket"]], r["frame_id"]))
    rp = os.path.join(DATA, f"seed_screen_review_{DATE}.csv")
    with open(rp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rev[0].keys())); w.writeheader(); w.writerows(rev)

    C = collections.Counter(lab[c]["bucket"] for c in todo)
    print(f"\nworks classified: {len(todo)}  {dict(C)}")
    print("agreement:", dict(collections.Counter(lab[c]["agreement"] for c in todo)))
    print(f"review sheet: {len(rev)} works "
          f"({dict(collections.Counter(r['machine_bucket'] for r in rev))})")
    print("wrote", p, "\nwrote", rp)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--runs", type=int, default=RUNS)
    ap.add_argument("--fresh", action="store_true",
                    help="ignore seed_screen_cache_<DATE>.jsonl and re-ask every record")
    a = ap.parse_args()
    rows, works = load_works()
    if a.dry_run:
        print(f"prompt_hash={PROMPT_HASH}  model={a.model}  runs={a.runs}")
        print(f"entries={len(rows)} works={len(works)} to classify={len(works)-len(SEED_SELF)}")
        print(f"calls: control {len(CONTROL_POS)+len(CONTROL_NEG)} + run "
              f"{(len(works)-len(SEED_SELF))*a.runs}\n")
        print("--- example user message (SF0087, a two-string work) ---")
        print(user_message(works["SF0087"]))
        sys.exit(0)
    k = os.environ.get("ANTHROPIC_API_KEY") or sys.exit("set ANTHROPIC_API_KEY")
    if a.validate:
        sys.exit(0 if validate(k, works, a.model) else 1)
    elif a.run:
        print(f"model={a.model}  runs={a.runs}  prompt_hash={PROMPT_HASH}\n")
        if not validate(k, works, a.model):
            sys.exit("control set failed -- fix the prompt before screening anything")
        run(k, rows, works, a.model, a.runs, a.fresh)
    else:
        ap.print_help()
