#!/usr/bin/env python3
"""
Collect publications for the Quarto site.

Pipeline
1. ORCID works summary  → title / year / journal / put-code / DOI
2. Crossref works       → richer metadata (authors, etc.)
3. Merge (Crossref wins, ORCID fills gaps)
4. Build TWO maps from ORCID bulk BibTeX:
      • doi_auth   : canonical DOI → author string
      • title_auth : normalised title (punctuation removed, lower-case) → author string
5. For every record whose author is blank or empty:
      • try doi_auth
      • else try title_auth
      • else (as last resort) download per-work BibTeX and parse authors
6. Write data/publications.yml

Dependencies: requests, pyyaml, bibtexparser
"""

from pathlib import Path
import os, sys, re, time, unicodedata, string
import requests, yaml, bibtexparser

# ───────────────────────── Helper functions ────────────────────────────
def g(node, *path):
    for k in path:
        if not isinstance(node, dict):
            return None
        node = node.get(k)
    return node

def canonical_doi(d):
    d = (d or "").strip().lower()
    return (
        d.replace("https://doi.org/", "")
         .replace("http://doi.org/", "")
         .replace("doi:", "")
    )

punct_xlate = str.maketrans("", "", string.punctuation)
def norm_title(t):
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = t.translate(punct_xlate)
    return " ".join(t.split())[:80]  # first 80 chars is plenty

def parse_bibtex_authors(tex: str) -> str:
    db = bibtexparser.loads(tex)
    if not db.entries:
        return ""
    names = db.entries[0].get("author", "")
    parts = [re.sub(r"[{}]", "", p).strip() for p in names.split(" and ")]
    parts = [p for p in parts if p]
    return "; ".join(parts)

def author_str(auth_json):
    return "; ".join(
        f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
        for a in auth_json
        if a.get("family") or a.get("given")
    )

# ───────────────────────── Config / session ────────────────────────────
ORCID  = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL  = os.getenv("CONTACT_EMAIL", "a.cangi@hzdr.de")

root = Path(__file__).resolve().parent.parent
data_dir = root / "data"
data_dir.mkdir(exist_ok=True, parents=True)
out_yaml = data_dir / "publications.yml"

session = requests.Session()
session.headers.update({"User-Agent": f"ml4md-publications/2.0 ({EMAIL})"})

# ───────────────────────── 1. ORCID summaries ──────────────────────────
summaries = session.get(
    f"https://pub.orcid.org/v3.0/{ORCID}/works",
    headers={"Accept": "application/json"}, timeout=30).json()

orc = []
for grp in summaries.get("group", []):
    s = grp["work-summary"][0]
    rec = {
        "put":     s["put-code"],
        "title":   g(s, "title", "title", "value") or "",
        "year":    g(s, "publication-date", "year", "value"),
        "journal": g(s, "journal-title", "value") or "",
        "author":  "",
    }
    for xid in g(s, "external-ids", "external-id") or []:
        if xid["external-id-type"].lower() == "doi":
            doi = canonical_doi(xid["external-id-value"])
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orc.append(rec)

print(f"ORCID summary records: {len(orc)}")

# ───────────────────────── 2. Crossref works ───────────────────────────
cr_items = session.get(
    f"https://api.crossref.org/works?filter=orcid:{ORCID}&rows=1000&mailto={EMAIL}",
    timeout=30
).json()["message"]["items"]

cross = []
for w in cr_items:
    cross.append(
        {
            "title":  g(w, "title", 0) or g(w, "short-title", 0) or "",
            "author": author_str(w.get("author", [])),
            "year":   g(w, "issued", "date-parts", 0, 0)
                      or g(w, "published-online", "date-parts", 0, 0)
                      or g(w, "created", "date-parts", 0, 0),
            "journal": g(w, "container-title", 0) or w.get("publisher", ""),
            "doi":     canonical_doi(w.get("DOI")),
            "href":    f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
        }
    )

print(f"Crossref records        : {len(cross)}")

# ───────────────────────── 3. Merge (Crossref wins) ────────────────────
by_doi = {r["doi"]: r for r in cross if r.get("doi")}
merged = cross.copy()

for r in orc:
    key = r.get("doi")
    if key and key in by_doi:
        base = by_doi[key]
        # keep put-code for later API if needed
        if r.get("put") and not base.get("put"):
            base["put"] = r["put"]
        for fld in ("title", "year", "journal", "author"):
            if not base.get(fld):
                base[fld] = r.get(fld)
    else:
        merged.append(r)

print(f"Merged unique records   : {len(merged)}")

# ───────────────────────── 4. Build BibTeX author maps ──────────────────
bib_tex = session.get(
    f"https://pub.orcid.org/v3.0/{ORCID}/works?format=bibtex",
    headers={"Accept": "application/x-bibtex"}, timeout=30).text

doi_auth, title_auth = {}, {}
for entry in bibtexparser.loads(bib_tex).entries:
    authors = parse_bibtex_authors(entry.get("author", ""))
    if not authors:
        continue
    doi     = canonical_doi(entry.get("doi") or entry.get("DOI"))
    if doi:
        doi_auth[doi] = authors
    title_auth[norm_title(entry.get("title"))] = authors

print(f"BibTeX items processed  : {len(doi_auth)} with DOI")

# ───────────────────────── 5. Author back-fill passes ──────────────────
filled_doi = filled_title = filled_work = 0

for rec in merged:
    if rec.get("author"):
        continue
    doi_key = rec.get("doi")
    if doi_key and doi_key in doi_auth:
        rec["author"] = doi_auth[doi_key]
        filled_doi += 1

for rec in merged:
    if rec.get("author"):
        continue
    tkey = norm_title(rec.get("title"))
    if tkey in title_auth:
        rec["author"] = title_auth[tkey]
        filled_title += 1

needs = [r for r in merged if not r.get("author") and r.get("put")]
for rec in needs:
    bib = session.get(
        f"https://pub.orcid.org/v3.0/{ORCID}/work/{rec['put']}/bibtex",
        headers={"Accept": "application/x-bibtex"}, timeout=30
    ).text
    auths = parse_bibtex_authors(bib)
    if auths:
        rec["author"] = auths
        filled_work += 1
    time.sleep(0.2)  # ≤5 req/s

print(f"Author filled via DOI   : {filled_doi}")
print(f"Author filled via title : {filled_title}")
print(f"Author filled per-work  : {filled_work}")

# ───────────────────────── 6. Write YAML ────────────────────────────────
for rec in merged:
    rec.pop("put", None)

merged.sort(key=lambda r: int(r["year"] or 0), reverse=True)

yaml.dump(merged, out_yaml.open("w", encoding="utf-8"),
          allow_unicode=True, sort_keys=False)

print(f"✓  Wrote {len(merged)} publications → {out_yaml}")
