#!/usr/bin/env python3
"""
check_arrivals.py -- arrival checks on every PDF in papers/journal/_incoming/ (pipeline piece 1).

Answers, per row of the retrieval sheet: is this the right paper, in the version the sheet claims,
complete and readable, with an appendix situation that matches the sheet? A failed check is a FLAG
for a human to adjudicate; nothing is blocked, moved or edited. Scope: notes/extraction_pipeline_scope.md
piece 1; tolerances: notes/retrieval_workflow.md ("Pipeline tolerances").

Checks
  sheet      every non-excluded row has <row_id>_main.pdf; `separate file` <=> <row_id>_supp.pdf;
             no file without a row; dropdown values valid (compared case-insensitively)
  readable   pdfinfo opens it, not encrypted, a text layer (>= MIN_CHARS_PER_PAGE on average),
             page count in a plausible range, not a saved login/error page
  identity   title (word coverage) and first-author surname on pages 1-2
  version    main_source = publisher: the row's DOI on pages 1-3, or a publisher/proceedings mark
             on pages 1-2, or fetched from a proceedings site; no arXiv stamp or preprint wording
             on page 1; publisher_url and doi_link name the same DOI
             main_source = arXiv: an arXiv stamp/id on pages 1-2 (info only)
             main_source = other repository: not checked
  appendix   in main PDF   -> an appendix-type heading on page >= 3 of the main PDF
             separate file -> the supp is readable, names the paper (title or author on pp.1-3, or the
                              title in its running heads),
                              and whether it repeats the main text (expected for arXiv copies)
             not found     -> the main text must not point to an appendix/e-companion
             `appendix_referenced_in_main` is recorded for every row (one of the three appendix facts).

Usage:  check_arrivals.py [SHEET_EXPORT_CSV]
        (default: newest data/audit_journal/04_retrieve/retrieval_sheet_export_*.csv)
Output: data/audit_journal/04_retrieve/arrival_checks_<date of the sheet export>.csv and a summary on stdout.
Text extracted from the PDFs is cached in papers/journal/_text_cache/ (outside the repo: copyrighted).
"""
import csv, hashlib, re, subprocess, sys, unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]                      # lookahead-premium-code/
ROOT = REPO.parent                          # Look Ahead Premium/
DATA = REPO / "data" / "audit_journal" / "04_retrieve"
INCOMING = ROOT / "papers" / "journal" / "_incoming"
CACHE = ROOT / "papers" / "journal" / "_text_cache"

MAIN_SOURCES = {"publisher", "arxiv (no published version)", "other repository (see notes)"}
APPENDIX_VALUES = {"in main pdf", "separate file", "not found"}
MIN_CHARS_PER_PAGE = 300
MAIN_PAGES = (4, 150)
TITLE_COVERAGE = 0.8          # share of the title's content words found on pp.1-2
REPEAT_SHARE = 0.5            # share of main p.1 8-word shingles found in the supp

PUBLISHER_MARKS = [            # lower-case substrings, searched on pp.1-2
    "pubsonline.informs.org", "informs", "sciencedirect", "elsevier", "springer", "ieee",
    "association for computing machinery", "acm reference format", "acm ", "mdpi", "lipics",
    "leibniz international proceedings", "taylor & francis", "taylor and francis", "wiley", "siam",
    "world scientific", "cambridge university press", "oxford university press", "jmlr",
    "journal of machine learning research", "journal of artificial intelligence research",
    "conference on neural information processing systems", "neurips", "advances in neural information",
    "proceedings of machine learning research", "pmlr", "proceedings of the",
    "published as a conference paper at iclr", "association for the advancement of artificial intelligence",
    "aaai", "international joint conference on artificial intelligence", "ijcai",
    "©", "copyright", "all rights reserved", "tandfonline", "https://doi.org/10.", "doi:10.",
    "conference on uncertainty in artificial intelligence",
]
PROCEEDINGS_SITES = ("papers.nips.cc", "proceedings.neurips.cc", "proceedings.mlr.press", "ojs.aaai.org",
                     "ijcai.org/proceedings")   # files the script fetched straight from the proceedings site
ARXIV_STAMP = re.compile(r"arxiv:\s*\d{4}\.\d{4,5}(v\d+)?\s*\[", re.I)
ARXIV_ID = re.compile(r"arxiv[:./\s]*(abs/)?\d{4}\.\d{4,5}", re.I)
PREPRINT_WORDS = re.compile(r"\b(preprint|submitted to|under review|accepted manuscript|author'?s? (accepted )?manuscript)\b", re.I)
LOGIN_WORDS = re.compile(r"\b(sign in|log in|login|access denied|institutional access|purchase this article|403 forbidden|page not found)\b", re.I)
APPENDIX_HEADING = re.compile(
    r"^\s*((\d+|[A-Z])\.?\s+)?(appendix|appendices|supplementary materials?|supplemental materials?|"
    r"supplementary information|e-?companion|electronic companion|online appendix|online supplement|"
    r"technical appendix)\b(?!\s*:)", re.I | re.M)
EC_HEADING = re.compile(r"^\s*EC\.?\s?1\.?\s*$|^\s*EC\.?\s?1\.?\s+[A-Z]", re.M)
APPENDIX_POINTER = re.compile(
    r"(online appendix|e-?companion|electronic companion|supplementary material|supplemental material|"
    r"online supplement|\bappendix\s+[A-Z]\b|\bappendix\s+EC|\bEC\.\d|\bin the appendix|\bsee appendix)", re.I)
SMALLCAPS_APPENDIX = re.compile(r"^\s*(A\.?\s+)?A\s?PPENDI(X|CES)\b", re.M)      # 'A PPENDIX' in ICLR small caps
REFERENCES_HEADING = re.compile(r"^\s*(\d+\.?\s+)?(references|bibliography|r\s?eferences)\s*$", re.I | re.M)
# ML-style lettered appendices after the references: 'A' (alone or with a title) ... then 'B' or 'A.1'
LETTER_A = re.compile(r"^\s*A\.?(\s*$|\s+[A-Z][A-Za-z])", re.M)
LETTER_A_ALONE = re.compile(r"^\s*A\.?\s*\n(\s*\n)?\s*[A-Z][A-Za-z\- ]{2,60}$", re.M)   # 'A' / 'Proof'
LETTER_A_INLINE = re.compile(r"^\s*A\.?\s{1,3}[A-Z][A-Za-z\- ]{2,60}$", re.M)            # 'A Proofs'
LETTER_B_INLINE = re.compile(r"^\s*(B|A\.1)\.?\s{1,3}[A-Z][A-Za-z\- ]{2,60}$", re.M)
LETTER_NEXT = re.compile(r"^\s*(B\.?(\s*$|\s+[A-Z][A-Za-z])|A\.1\.?(\s*$|\s+[A-Z]))", re.M)
INFORMS_HEADER_LINE = re.compile(r"^\s*supplemental material:.*$", re.I | re.M)
STOP = set("a an and the of for in on with to via by from at as is are its into under over using toward towards".split())


# ---------------------------------------------------------------- text helpers
def pdfinfo(path):
    r = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, errors="replace")
    info = {}
    for line in r.stdout.splitlines():
        k, _, v = line.partition(":")
        info[k.strip()] = v.strip()
    return r.returncode, info


def pages_text(path):
    """List of page texts, cached by the file's sha256."""
    h = sha256(path)
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"{h}.txt"
    if not cf.exists():
        r = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, errors="replace")
        cf.write_text(r.stdout)
    return cf.read_text().split("\f")


_sha = {}
def sha256(path):
    if path not in _sha:
        _sha[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _sha[path]


def squash(s):
    """Lower-case alphanumerics only, two ways: accents stripped to ASCII, and accented letters dropped
    (the sheet's own names drop them, e.g. 'EstebanPrez')."""
    s = unicodedata.normalize("NFKC", s).lower()
    ascii_ = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_), re.sub(r"[^a-z0-9]", "", s)


def words(s):
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", s)).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", s)


def title_coverage(title, text):
    tw = [w for w in words(title) if w not in STOP and len(w) > 2]
    if not tw:
        return 1.0
    blob = squash(text)[0]          # hyphenation and line breaks are squashed away
    return sum(w in blob for w in tw) / len(tw)


def author_found(surname, text):
    if not surname.strip():
        return True
    a1, a2 = squash(surname)
    t1, t2 = squash(text)
    return (a1 and a1 in t1) or (a2 and a2 in t2) or (a1 and a1 in t2)


def shingles(text, n=8):
    w = words(text)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def row_doi(row):
    for k in ("publisher_url", "doi_link"):
        m = re.search(r"doi\.org/(10\.\d{4,9}/\S+)", row.get(k, "") or "")
        if m and "arxiv" not in m.group(1).lower():
            return m.group(1).rstrip(".").lower()
    return ""


# ---------------------------------------------------------------- checks
def check_file(path, kind):
    """Readability checks common to main and supp. Returns (pages_list|None, facts dict, flags list)."""
    facts, flags = {}, []
    try:
        sha256(path)
    except OSError as e:          # Dropbox online-only placeholder: README.md, "Resource deadlock avoided"
        return None, {"pages": 0}, [f"{kind}: cannot read file ({e.strerror}, Dropbox online-only?)"]
    rc, info = pdfinfo(path)
    if rc != 0:
        return None, {"pages": 0}, [f"{kind}: pdfinfo cannot open"]
    if info.get("Encrypted", "no").lower().startswith("yes"):
        flags.append(f"{kind}: encrypted")
    n = int(info.get("Pages", "0") or 0)
    facts["pages"] = n
    pages = pages_text(path)
    chars = sum(len(p.strip()) for p in pages)
    facts["chars_per_page"] = round(chars / max(n, 1))
    if facts["chars_per_page"] < MIN_CHARS_PER_PAGE:
        flags.append(f"{kind}: little or no text layer ({facts['chars_per_page']} chars/page)")
    if kind == "main" and not (MAIN_PAGES[0] <= n <= MAIN_PAGES[1]):
        flags.append(f"main: implausible page count ({n})")
    if n <= 3 and LOGIN_WORDS.search(" ".join(pages[:2])):
        flags.append(f"{kind}: looks like a login or error page")
    return pages, facts, flags


def check_row(row, files):
    rid = row["row_id"]
    ms = row["main_source"].strip().lower()
    ap = row["appendix"].strip().lower()
    out = {"row_id": rid, "assigned_to": row["assigned_to"], "main_source": row["main_source"],
           "appendix": row["appendix"]}
    flags = []
    excluded = row["notes"].strip().lower().startswith("excluded")
    main, supp = INCOMING / f"{rid}_main.pdf", INCOMING / f"{rid}_supp.pdf"
    has_main, has_supp = main.name in files, supp.name in files

    # ---- sheet
    if excluded:
        out["status"] = "excluded"
        if has_main or has_supp:
            flags.append("sheet: excluded row has files")
        out["flags"] = " | ".join(flags)
        return out
    if ms not in MAIN_SOURCES:
        flags.append(f"sheet: main_source {row['main_source']!r}")
    if ap not in APPENDIX_VALUES:
        flags.append(f"sheet: appendix {row['appendix']!r}")
    if not has_main:
        flags.append("sheet: no main PDF")
        out["flags"] = " | ".join(flags); out["status"] = "FLAG"
        return out
    if ap == "separate file" and not has_supp:
        flags.append("sheet: 'separate file' but no supp PDF")
    if ap != "separate file" and has_supp:
        flags.append(f"sheet: supp PDF present but appendix is {row['appendix']!r}")

    m1 = re.search(r"doi\.org/(10\.\S+)", row.get("publisher_url", "") or "")
    m2 = re.search(r"doi\.org/(10\.\S+)", row.get("doi_link", "") or "")
    if m1 and m2 and m1.group(1).lower() != m2.group(1).lower() and ms == "publisher":
        flags.append(f"sheet: publisher_url DOI {m1.group(1)} differs from doi_link DOI {m2.group(1)}")

    # ---- readable
    pages, f, fl = check_file(main, "main")
    flags += fl
    out["main_pages"] = f.get("pages", 0)
    if pages is None:
        out["flags"] = " | ".join(flags); out["status"] = "FLAG"
        return out
    out["main_sha256"] = sha256(main)
    p12, p13, p1 = " ".join(pages[:2]), " ".join(pages[:3]), pages[0]

    # ---- identity
    cov = title_coverage(row["title"], p12)
    out["title_coverage"] = round(cov, 2)
    if cov < TITLE_COVERAGE:
        flags.append(f"identity: title not on pp.1-2 (coverage {cov:.2f})")
    out["author_found"] = author_found(row["first_author"], p12)
    if not out["author_found"]:
        flags.append(f"identity: first author {row['first_author']!r} not on pp.1-2")

    # ---- version
    doi = row_doi(row)
    low12 = p12.lower()
    stamp = bool(ARXIV_STAMP.search(p12))
    if ms == "publisher":
        ev = []
        if doi and doi in re.sub(r"\s+", "", p13.lower()):
            ev.append("doi")
        ev += [m.strip() for m in PUBLISHER_MARKS if m in low12][:3]
        if any(site in (row.get("publisher_url") or "") for site in PROCEEDINGS_SITES):
            ev.append("proceedings site")
        out["version_evidence"] = ", ".join(ev)
        if not ev:
            flags.append("version: no DOI or publisher/proceedings mark on pp.1-3")
        if stamp:
            flags.append("version: arXiv stamp on pp.1-2 of a 'publisher' file")
        pw = PREPRINT_WORDS.search(p1)
        if pw:
            flags.append(f"version: preprint wording on p.1 ({pw.group(0)!r})")
    elif ms.startswith("arxiv"):
        out["version_evidence"] = "arXiv stamp" if stamp else ("arXiv id" if ARXIV_ID.search(p12) else "")
        if not out["version_evidence"]:
            flags.append("version: 'arXiv' row but no arXiv stamp/id on pp.1-2 (check)")
    else:
        out["version_evidence"] = "n/a (other repository)"

    # ---- appendix
    body = "\f".join(pages)
    body_wo_header = INFORMS_HEADER_LINE.sub("", body)
    late = "\f".join(pages[2:])
    heading = bool(APPENDIX_HEADING.search(late) or EC_HEADING.search(late) or SMALLCAPS_APPENDIX.search(late))
    if not heading:
        refs = list(REFERENCES_HEADING.finditer(late))
        tail = late[refs[-1].end():] if refs else ""
        a = LETTER_A.search(tail)
        heading = bool(a and LETTER_NEXT.search(tail, a.end()))
    if not heading:                 # appendix placed before the references, or a lone 'A' section
        second_half = "\f".join(pages[max(2, len(pages) // 2):])
        a = LETTER_A_INLINE.search(second_half)
        heading = bool(LETTER_A_ALONE.search(second_half) or (a and LETTER_B_INLINE.search(second_half, a.end())))
    out["appendix_heading_in_main"] = heading
    out["appendix_referenced_in_main"] = bool(APPENDIX_POINTER.search(body_wo_header))
    if ap == "in main pdf" and not heading:
        flags.append("appendix: 'in main PDF' but no appendix heading found")
    if ap == "not found" and out["appendix_referenced_in_main"]:
        m = APPENDIX_POINTER.search(body_wo_header)
        flags.append(f"appendix: 'not found' but main text points to one ({m.group(0)!r})")
    if has_supp:
        spages, sf, sfl = check_file(supp, "supp")
        flags += sfl
        out["supp_pages"] = sf.get("pages", 0)
        if spages is not None:
            out["supp_sha256"] = sha256(supp)
            s13 = " ".join(spages[:3])
            names = (title_coverage(row["title"], s13) >= 0.6 or author_found(row["first_author"], s13)
                     or title_coverage(row["title"], "\f".join(spages)) >= TITLE_COVERAGE)  # running heads
            out["supp_names_paper"] = names
            if not names:
                flags.append("supp: neither title nor first author on pp.1-3 (check it is this paper's)")
            sh_main = shingles(pages[0])
            share = len(sh_main & shingles("\f".join(spages))) / max(len(sh_main), 1)
            out["supp_repeats_main"] = share >= REPEAT_SHARE
    out["flags"] = " | ".join(flags)
    out["status"] = "FLAG" if flags else "ok"
    return out


def main():
    if len(sys.argv) > 1:
        sheet = Path(sys.argv[1])
    else:
        sheet = sorted(DATA.glob("retrieval_sheet_export_*.csv"))[-1]
    stamp = re.search(r"(\d{4}-\d{2}-\d{2})", sheet.name).group(1)
    rows = list(csv.DictReader(open(sheet, encoding="utf-8-sig")))
    files = {p.name for p in INCOMING.glob("*.pdf")}
    ids = {r["row_id"] for r in rows}
    results = []
    for i, r in enumerate(rows, 1):
        results.append(check_row(r, files))
        if i % 50 == 0:
            print(f"  {i}/{len(rows)} rows", file=sys.stderr, flush=True)
    orphans = sorted(f for f in files if f.split("_")[0] not in ids)

    cols = ["row_id", "assigned_to", "status", "flags", "main_source", "appendix", "main_pages",
            "title_coverage", "author_found", "version_evidence", "appendix_heading_in_main",
            "appendix_referenced_in_main", "supp_pages", "supp_names_paper", "supp_repeats_main",
            "main_sha256", "supp_sha256"]
    out = DATA / f"arrival_checks_{stamp}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    st = Counter(r["status"] for r in results)
    kinds = Counter(f.split(":")[0] + ": " + re.sub(r"\s*\(.*", "", f.split(":", 1)[1].strip())
                    for r in results for f in filter(None, r.get("flags", "").split(" | ")))
    print(f"sheet {sheet.name}: {len(rows)} rows; {len(files)} PDFs in _incoming/; orphans {orphans or 'none'}")
    print("status:", dict(st))
    for k, n in kinds.most_common():
        print(f"  {n:4d}  {k}")
    print(f"wrote {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
