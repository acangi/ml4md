#!/usr/bin/env python3
"""
Collect publications for the Quarto site (GitHub Actions).

Workflow
1. ORCID summaries  → title / year / journal / put-code / DOI
2. Crossref works   → richer metadata when available
3. Merge            (Crossref wins, ORCID fills gaps, keep put-code)
4. For EVERY record call /work/<PUT>/bibtex   (≈ 50 calls, 5 req/s)
   • parse author list with bibtexparser
5. Write data/publications.yml
"""

import os, sys, time, re, unicodedata, string
from pathlib import Path
import requests, yaml, bibtexparser

# ── helpers ───────────────────────────────────────────────────────────────
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

def parse_bibtex_authors(tex: str) -> str:
    db = bibtexparser.loads(tex)
    if not db.entries:
        return ""
    names = db.entries[0].get("author", "")
    parts = [re.sub(r"[{}]", "", p).strip() for p in names.split(" and ")]
    parts = [p for p in parts if p]
    return "; ".join(parts)

punct = str.maketrans("", "", string.punctuation)
def normalise_title(t):
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = t.translate(punct)
    return " ".join(t.split())[:80]

def author_str(a_json):
    return "; ".join(
        f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
        for a in a_json if a.get('family') or a.get('given')
    )

# ── config & session ──────────────────────────────────────────────────────
ORCID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL = os.getenv("CONTACT_EMAIL", "a.cangi@hzdr.de")

root = Path(__file__).resolve().parent.parent
data_dir = root / "data"
data_dir.mkdir(exist_ok=True, parents=True)
out_yaml = data_dir / "publications.yml"

session = requests.Session()
session.headers.update({"User-Agent": f"ml4md-publications/3.0 ({EMAIL})"})

# ── 1. ORCID summaries ────────────────────────────────────────────────────
summaries = session.get(
    f"https://pub.orcid.org/v3.0/{ORCID}/works",
    headers={"Accept": "application/json"}, timeout=30
).json()

orc = []
for grp in summaries.get("group", []):
    s = grp["work-summary"][0]
    rec = {
        "put":     s["put-code"],
        "title":   g(s, "title", "title", "value") or "",
        "year":    g(s, "publication-date", "year", "value"),
        "journal": g(s, "journal-title", "value") or "",
    }
    for xid in g(s, "external-ids", "external-id") or []:
        if xid["external-id-type"].lower() == "doi":
            doi = canonical_doi(xid["external-id-value"])
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orc.append(rec)

print(f"ORCID summary records: {len(orc)}")

# ── 2. Crossref works ─────────────────────────────────────────────────────
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

# ── 3. Merge (Crossref wins) ──────────────────────────────────────────────
by_doi = {r["doi"]: r for r in cross if r.get("doi")}
merged = cross.copy()

for r in orc:
    key = r.get("doi")
    if key and key in by_doi:
        base = by_doi[key]
        if r.get("put") and not base.get("put"):
            base["put"] = r["put"]
        for fld in ("title", "year", "journal"):
            if not base.get(fld):
                base[fld] = r.get(fld)
    else:
        merged.append(r)

print(f"Merged unique records   : {len(merged)}")

# ── 4. ALWAYS fetch per-work BibTeX to get authors ───────────────────────
filled = 0
for rec in merged:
    bib = session.get(
        f"https://pub.orcid.org/v3.0/{ORCID}/work/{rec['put']}/bibtex",
        headers={"Accept": "application/x-bibtex"}, timeout=30
    ).text
    auths = parse_bibtex_authors(bib)
    if auths:
        rec["author"] = auths
        filled += 1
    time.sleep(0.2)    # 5 requests / s

print(f"Author filled via BibTeX: {filled}")

# ── 5. Write YAML ─────────────────────────────────────────────────────────
for rec in merged:
    rec.pop("put", None)

merged.sort(key=lambda r: int(r["year"] or 0), reverse=True)

yaml.dump(merged, out_yaml.open("w", encoding="utf-8"),
          allow_unicode=True, sort_keys=False)

print(f"✓  Wrote {len(merged)} publications → {out_yaml}")
