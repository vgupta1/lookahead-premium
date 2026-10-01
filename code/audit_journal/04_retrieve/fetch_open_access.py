#!/usr/bin/env python3
"""
fetch_open_access.py -- fetch open-access papers (and appendices) for rows of papers_to_obtain.csv

Scripted counterpart of the students' manual retrieval (notes/retrieval_workflow.md). Same rules,
same outputs: <row_id>_main.pdf and, when the appendix is not in the main PDF, <row_id>_supp.pdf,
written to an intake folder; plus one line per row with the retrieval sheet's student columns
(main_source, publisher_url, arxiv_url_if_needed, appendix, notes) so the sheet stays the single
record of how every paper was obtained.

A row the script cannot settle cleanly is NOT guessed at: it is reported `manual` with the reason,
and goes on the students' list. Settled cleanly means the landing page's title matches ours.

Routes (column `access_route`): neurips, pmlr, aaai, ijcai, arxiv. openreview is resolved to its
landing page but always handed to manual: its PDFs sit behind a bot challenge.

Appendix, in the protocol's order: in the main PDF? -> publisher supplement -> latest arXiv version.
"No author sites." An arXiv copy used as the appendix source is the whole arXiv paper, saved as
<row_id>_supp.pdf. A _supp.pdf may therefore repeat the main text; it is saved whole, never split
(VG, 2026-09-29): body facts come from _main.pdf, only the appendix from _supp.pdf.

Every fetched main PDF must show the paper's title on page 1 or 2, or the row goes to manual.

Usage:  fetch_open_access.py PAPERS_CSV OUT_DIR ROW_ID [ROW_ID ...]
"""
import csv, difflib, gzip, io, json, re, subprocess, sys, time, zipfile, html
from datetime import date
from pathlib import Path
import requests

UA = {"User-Agent": "lookahead-premium-audit/0.1 (mailto:guptavis@usc.edu)"}
S = requests.Session(); S.headers.update(UA)
_cache = {}


def get(url, **kw):
    if url in _cache and not kw:
        return _cache[url]
    for attempt in range(4):
        r = S.get(url, timeout=90, **kw)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1)); continue
        break
    if not kw:
        _cache[url] = r
    return r


def norm(t):
    t = html.unescape(t or "").lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def same_title(a, b, thresh=0.93):
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and difflib.SequenceMatcher(None, a, b).ratio() >= thresh


# ---------------------------------------------------------------- resolvers
# each returns dict(title=, landing=, pdf=, supp=[urls]) or raises Manual(reason)
class Manual(Exception):
    pass


def crossref_doi(row, prefix):
    """Find a DOI with the given registrant prefix by bibliographic search, title-verified."""
    r = get("https://api.crossref.org/works", params={
        "query.bibliographic": row["title"], "query.author": row["first_author"], "rows": 10})
    for it in r.json()["message"]["items"]:
        if it["DOI"].startswith(prefix) and same_title((it.get("title") or [""])[0], row["title"]):
            return it["DOI"]
    return None


def crossref_record(doi, row):
    """Crossref's record for a DOI, or None if it does not resolve or is a different paper."""
    if not doi:
        return None
    r = get(f"https://api.crossref.org/works/{doi}")
    if r.status_code != 200:
        return None
    m = r.json()["message"]
    return m if same_title((m.get("title") or [""])[0], row["title"]) else None


def neurips(row):
    yr = row["year"]
    base = "https://papers.nips.cc"
    cands = []
    for y in (yr, str(int(yr) + 1), str(int(yr) - 1)):
        page = get(f"{base}/paper_files/paper/{y}").text
        pages = [page] + [get(base + h).text for h in
                          set(re.findall(r'href="(/paper_files/paper/%s/[^"#]*main-conference)"' % y, page))]
        for p in pages:
            for href, t in re.findall(r'title="paper title" href="([^"]+)">([^<]+)', p):
                if same_title(t, row["title"]):
                    cands.append((href, t))
        if cands:
            break
    if not cands:
        raise Manual("no title match in NeurIPS proceedings (year +/-1)")
    href, t = cands[0]
    landing = base + href
    a = get(landing).text
    links = dict((lab, h) for h, lab in re.findall(r"href='([^']+)'>([A-Za-z]+)</a>", a))
    if "Paper" not in links:
        raise Manual("NeurIPS page has no Paper link")
    supp = [base + links[k] for k in ("Supplemental", "Supplementary") if k in links]
    return dict(title=html.unescape(t), landing=landing, pdf=base + links["Paper"], supp=supp)


def pmlr(row):
    idx = get("https://proceedings.mlr.press/").text
    vols = re.findall(r'<a href="(v\d+)"><b>Volume \d+</b></a>\s*([^<]+)</li>', idx)
    ref = row["reference"] + " " + row["venue"]
    want = ("ICML",) if re.search(r"ICML|International Conference on Machine Learning", ref) else \
           ("AISTATS",) if re.search(r"AISTATS|Artificial Intelligence and Statistics", ref) else \
           ("ICML", "AISTATS")
    yr = int(row["year"])
    for y in (yr, yr + 1, yr - 1):
        for v, desc in vols:
            if str(y) in desc and any(w in desc for w in want):
                p = get(f"https://proceedings.mlr.press/{v}/").text
                for block in p.split('<div class="paper">')[1:]:
                    m = re.search(r'<p class="title">(.*?)</p>', block, re.S)
                    if m and same_title(m.group(1), row["title"]):
                        hrefs = re.findall(r'href="([^"]+)"', block)
                        landing = next(h for h in hrefs if h.endswith(".html"))
                        pdf = next(h for h in hrefs if h.endswith(".pdf") and "supp" not in h)
                        supp = [h for h in hrefs if "supp" in h.lower()]
                        return dict(title=html.unescape(m.group(1)).strip(), landing=landing,
                                    pdf=pdf.replace("http://", "https://"),
                                    supp=[s.replace("http://", "https://") for s in supp])
    raise Manual(f"no title match in PMLR {want} volumes (year +/-1)")


def aaai(row):
    m = crossref_record(row["doi"], row)          # the list's DOI, if it resolves to this paper
    if m is None:                                  # else search (Scopus DOIs are occasionally malformed)
        doi = crossref_doi(row, "10.1609/")
        m = crossref_record(doi, row) if doi else None
    if m is None:
        raise Manual("no AAAI DOI found that resolves to this title")
    doi, title = m["DOI"], (m.get("title") or [""])[0]
    landing = m["resource"]["primary"]["URL"]
    p = get(landing).text
    g = re.search(r'obj_galley_link pdf" href="([^"]+)"', p)
    if not g:
        raise Manual("AAAI page has no PDF galley")
    return dict(title=title, landing=landing, pdf=g.group(1).replace("/article/view/", "/article/download/"),
                supp=[], doi=doi)  # AAAI OJS publishes no supplements; other galleys are video/poster


def ijcai(row):
    m = crossref_record(row["doi"], row)          # the list's DOI, if it resolves to this paper
    if m is None:                                  # else search (Scopus DOIs are occasionally malformed)
        doi = crossref_doi(row, "10.24963/")
        m = crossref_record(doi, row) if doi else None
    if m is None:
        raise Manual("no IJCAI DOI found that resolves to this title")
    doi, title = m["DOI"], (m.get("title") or [""])[0]
    y, n = re.search(r"ijcai\.(\d{4})/(\d+)", doi).groups()
    return dict(title=title, landing=f"https://www.ijcai.org/proceedings/{y}/{int(n)}",
                pdf=f"https://www.ijcai.org/proceedings/{y}/{int(n):04d}.pdf", supp=[], doi=doi)


def openreview(row):
    words = " ".join(row["title"].split()[:8])
    r = get("https://api2.openreview.net/notes/search", params={"term": words, "limit": 25, "source": "forum"})
    for n in r.json().get("notes", []):
        c = n["content"]; t = c.get("title", {}).get("value", "")
        if same_title(t, row["title"]) and "ICLR" in c.get("venue", {}).get("value", ""):
            raise Manual(f"OpenReview PDFs are behind a bot challenge; landing page "
                         f"https://openreview.net/forum?id={n['forum']}")
    raise Manual("OpenReview PDFs are behind a bot challenge; no ICLR title match found either")


def arxiv_search(title, author):
    """arXiv id for a title: exact-phrase title search first, then all-significant-words + author."""
    clean = re.sub(r"[^A-Za-z0-9 ]+", " ", title).split()
    words = [w for w in clean if len(w) > 3][:8]
    surname = re.sub(r"[^A-Za-z]", "", author)
    queries = ['ti:"%s"' % " ".join(clean)]
    if words:
        queries.append(" AND ".join(f"ti:{w}" for w in words) + (f" AND au:{surname}" if surname else ""))
    for q in queries:
        r = get("https://export.arxiv.org/api/query", params={"search_query": q, "max_results": 10})
        for e in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
            t = re.search(r"<title>(.*?)</title>", e, re.S).group(1)
            aid = re.search(r"<id>http://arxiv.org/abs/([^<]+)</id>", e).group(1)
            if same_title(t, title, 0.9) and author.lower()[:5] in e.lower():
                return re.sub(r"v\d+$", "", aid), " ".join(t.split())
        time.sleep(3)   # arXiv asks for <= 1 request / 3 s
    return None, None


def published_version(row):
    """A DOI for a journal/proceedings version of a preprint, if Crossref has one."""
    r = get("https://api.crossref.org/works", params={
        "query.bibliographic": row["title"], "query.author": row["first_author"], "rows": 10})
    for it in r.json()["message"]["items"]:
        if it.get("type") in ("journal-article", "proceedings-article", "book-chapter") and \
           not it["DOI"].startswith("10.48550") and \
           same_title((it.get("title") or [""])[0], row["title"], 0.9) and \
           any(row["first_author"].lower() in (a.get("family") or "").lower() for a in it.get("author", [])):
            return it["DOI"], (it.get("container-title") or [""])[0]
    return None, None


def arxiv_id_in_reference(ref):
    m = re.search(r"arXiv[:\s]*(\d{4})\.\s*(\d{4,5})", ref)
    return f"{m.group(1)}.{m.group(2)}" if m else None


def arxiv_title(aid, author=""):
    """Latest arXiv title for an id, or None if the id's authors do not include `author`."""
    r = get("https://export.arxiv.org/api/query", params={"id_list": aid})
    m = re.search(r"<entry>(.*?)</entry>", r.text, re.S)
    if not m or (author and author.lower()[:5] not in m.group(1).lower()):
        return None
    return " ".join(re.search(r"<title>(.*?)</title>", m.group(1), re.S).group(1).split())


def arxiv(row):
    aid = arxiv_id_in_reference(row["reference"])
    t = arxiv_title(aid, row["first_author"]) if aid else None
    if aid and not t:
        aid = None                           # the cited id is not by this first author
    # a cited id whose title changed across versions is kept: arXiv's latest title is what we
    # search Crossref with, and the note records the change
    retitled = bool(t) and not same_title(t, row["title"], 0.85)
    probe = dict(row, title=t or row["title"])   # search Crossref on arXiv's own title spelling
    doi, venue = published_version(probe)
    if doi:
        raise Manual(f"published version exists: doi:{doi} ({venue}) -- fetch that instead")
    if not aid:
        aid, t = arxiv_search(row["title"], row["first_author"])
    if not aid:
        raise Manual("not found on arXiv by title")
    return dict(title=t, landing=f"https://arxiv.org/abs/{aid}", pdf=f"https://arxiv.org/pdf/{aid}",
                supp=[], arxiv=True,
                note=(f"arXiv {aid} cited by the survey; retitled on arXiv as: {t}" if retitled else ""))


ROUTE = dict(neurips=neurips, pmlr=pmlr, aaai=aaai, ijcai=ijcai, openreview=openreview, arxiv=arxiv)

# ---------------------------------------------------------------- appendix detection
APPX_HEAD = re.compile(r"^\s*(?:[A-Z]\.?\s+)?(appendix|appendices|supplementary material|"
                       r"supplementary materials|technical appendix|e-companion|online appendix)\b",
                       re.I | re.M)
LETTER_SEC = re.compile(r"^\s*[A-F](?:\.\d+)?\s{1,3}[A-Z][A-Za-z][^\n]{2,80}$", re.M)
REFS = re.compile(r"^\s*(references|bibliography)\s*$", re.I | re.M)


def pdf_text(b):
    p = subprocess.run(["pdftotext", "-", "-"], input=b, capture_output=True)
    return p.stdout.decode("utf-8", "ignore")


def appendix_in_pdf(text):
    """True if an appendix section starts after the (first) reference list. The first, because an
    appendix often carries a reference list of its own after it."""
    refs = [m.start() for m in REFS.finditer(text)]
    tail = text[refs[0] if refs else int(len(text) * 0.6):]
    # also accept an appendix placed before the references (some templates do that)
    return bool(APPX_HEAD.search(tail) or LETTER_SEC.search(tail) or
                re.search(r"^\s*(appendix|appendices)\s*$", text, re.I | re.M))


def fetch_pdf(url):
    r = S.get(url, timeout=180)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        raise Manual(f"download failed ({r.status_code}, {r.headers.get('content-type')}) {url}")
    return r.content


def supp_pdf(url):
    """A supplement as a single PDF: a PDF as-is; from a zip, the one PDF in it (else manual)."""
    r = S.get(url, timeout=300)
    if r.status_code != 200:
        raise Manual(f"supplement download failed ({r.status_code}) {url}")
    if r.content.startswith(b"%PDF"):
        return r.content, ""
    if r.content[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(r.content))
        pdfs = [n for n in z.namelist() if n.lower().endswith(".pdf") and "__MACOSX" not in n]
        named = [n for n in pdfs if re.search(r"supp|appendix|appx", n, re.I) and "/code/" not in n.lower()]
        pick = pdfs if len(pdfs) == 1 else named if len(named) == 1 else []
        if pick:
            return z.read(pick[0]), f"supplement taken from {pick[0]} inside the zip"
        if not pdfs:
            return None, "supplement zip holds no PDF (code/data only)"
        raise Manual(f"supplement zip holds {len(pdfs)} PDFs: {pdfs[:5]}")
    raise Manual(f"supplement is neither PDF nor zip: {url}")


# ---------------------------------------------------------------- one row
def do_row(row, out):
    rid = row["venue_paper_id"] or row["survey_ref_id"]
    rec = dict(row_id=rid, status="", main_source="", publisher_url="",
               arxiv_url_if_needed="", appendix="", notes="", matched_title="")
    try:
        f = ROUTE.get(row["access_route"])
        if not f:
            raise Manual(f"route {row['access_route']} is not scripted")
        hit = f(row)
        rec["matched_title"] = hit["title"]
        main = fetch_pdf(hit["pdf"])
        first = subprocess.run(["pdftotext", "-l", "2", "-", "-"], input=main,
                               capture_output=True).stdout.decode("utf-8", "ignore")
        def shown(t):
            t = norm(t)[:40]; m = difflib.SequenceMatcher(None, t, norm(first), autojunk=False).find_longest_match(0, len(t), 0, len(norm(first)))
            return m.size >= 0.75 * len(t)
        if not (shown(row["title"]) or shown(hit["title"])):
            raise Manual(f"downloaded PDF does not show the title on page 1-2: {hit['pdf']}")
        is_arxiv = hit.get("arxiv", False)
        rec["main_source"] = "arXiv (no published version)" if is_arxiv else "publisher"
        if is_arxiv:
            rec["arxiv_url_if_needed"] = hit["landing"]
        else:
            doi = hit.get("doi") or row["doi"]
            rec["publisher_url"] = f"https://doi.org/{doi}" if doi else hit["landing"]
            if hit.get("doi") and row["doi"] and hit["doi"].lower() != row["doi"].lower():
                rec["notes"] = f"list DOI {row['doi']} does not resolve to this paper; correct DOI {hit['doi']}"
        (out / f"{rid}_main.pdf").write_bytes(main)
        notes = []
        if appendix_in_pdf(pdf_text(main)):
            rec["appendix"] = "in main PDF"
        else:
            supp = None
            for u in hit["supp"]:
                supp, why = supp_pdf(u)
                if why: notes.append(why)
                if supp: break
            if supp is None and not is_arxiv:
                aid, _ = arxiv_search(row["title"], row["first_author"])
                if aid:
                    ab = fetch_pdf(f"https://arxiv.org/pdf/{aid}")
                    if appendix_in_pdf(pdf_text(ab)):
                        supp = ab
                        rec["arxiv_url_if_needed"] = f"https://arxiv.org/abs/{aid}"
                        notes.append("appendix from arXiv (whole arXiv paper saved as supp)")
                    else:
                        rec["arxiv_url_if_needed"] = f"https://arxiv.org/abs/{aid}"
                        notes.append("arXiv version checked: no appendix")
                else:
                    notes.append("not found on arXiv")
            if supp is not None:
                (out / f"{rid}_supp.pdf").write_bytes(supp)
                rec["appendix"] = "separate file"
            else:
                rec["appendix"] = "not found"
        if hit.get("note"):
            notes.insert(0, hit["note"])
        if rec["notes"]:
            notes.insert(0, rec["notes"])
        rec["notes"] = "; ".join(notes)
        rec["status"] = "done"
    except Exception as e:           # Manual, or anything unexpected: never guess, hand it over
        rec["status"] = "manual"
        rec["notes"] = str(e) if isinstance(e, Manual) else f"script error: {type(e).__name__}: {e}"[:300]
        for p in out.glob(f"{rid}_*.pdf"):
            p.unlink()
    return rec


def main():
    src, out, ids = Path(sys.argv[1]), Path(sys.argv[2]), set(sys.argv[3:])
    if ids == {"ALL"}:  # every row on a scripted route
        ids = {r["venue_paper_id"] or r["survey_ref_id"] for r in csv.DictReader(open(src, encoding="utf-8"))
               if r["access_route"] in ROUTE}
    out.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(open(src, newline="", encoding="utf-8"))
            if (r["venue_paper_id"] or r["survey_ref_id"]) in ids]
    done_path = out / "_progress.jsonl"   # resumable: rows already settled are not refetched
    done = {}
    if done_path.exists():
        for line in open(done_path):
            d = json.loads(line); done[d["row_id"]] = d
    recs = []
    for r in rows:
        rid = r["venue_paper_id"] or r["survey_ref_id"]
        if rid in done:
            recs.append(done[rid]); continue
        rec = do_row(r, out); recs.append(rec)
        with open(done_path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"{rec['row_id']:7s} {r['access_route']:10s} {r['year']} {rec['status']:6s} {rec['appendix']:13s} {rec['notes'][:110]}", flush=True)
    log = out / f"_scripted_{date.today().isoformat()}.csv"
    with open(log, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(recs[0])); w.writeheader(); w.writerows(recs)
    print(f"-> {log}")


if __name__ == "__main__":
    main()
