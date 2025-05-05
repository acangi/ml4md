#!/usr/bin/env python3
"""
Harvest publications from
 • ORCID (all works, any DOI agency, or none)  → titles / years / journals
 • Crossref (DOIs registered with Crossref)     → rich metadata incl. authors
Then:
 • Fetch full ORCID work records *only when* author field is still blank
   (1 GET per missing item, well within ORCID’s public-API rate-limit).
Writes data/publications.yml for Quarto’s listing page.
"""
from pathlib import Path
import os, sys, json, requests, yaml, time

# ── helpers ────────────────────────────────────────────────────────────────
def g(node, *path):
    """Safe nested .get(); returns None if chain breaks."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node

def name(a):
    """Given ORCID or Crossref author dict return 'Given Family'."""
    return f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()

def author_str(author_list):
    return "; ".join([name(a) for a in author_list if name(a)])

# ── config ─────────────────────────────────────────────────────────────────
ORCID_ID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL    = os.getenv("CONTACT_EMAIL", "webmaster@example.org")  # polite pool

root     = Path(__file__).resolve().parent.parent
data_dir = root / "data"
data_dir.mkdir(exist_ok=True, parents=True)
out_yaml = data_dir / "publications.yml"

session = requests.Session()
session.headers.update({"User-Agent": f"ml4md-publications/1.0 ({EMAIL})"})

# ── 1. ORCID summaries ────────────────────────────────────────────────────
orcid_url = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
summaries = session.get(orcid_url, headers={"Accept": "application/json"},
                        timeout=30).json()

orcid_records = []
for grp in summaries.get("group", []):
    s  = grp["work-summary"][0]
    pc = s["put-code"]                      # we'll need this if author blank
    rec = {
        "put-code": pc,
        "title":   g(s, "title", "title", "value") or "",
        "year":    g(s, "publication-date", "year", "value"),
        "journal": g(s, "journal-title", "value") or "",
        "author":  "",                      # filled later if we fetch full record
    }
    for xid in g(s, "external-ids", "external-id") or []:
        if xid["external-id-type"].lower() == "doi":
            doi = xid["external-id-value"].lower()
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orcid_records.append(rec)

# ── 2. Crossref works ──────────────────────────────────────────────────────
cr_url = f"https://api.crossref.org/works?filter=orcid:{ORCID_ID}&rows=1000&mailto={EMAIL}"
crossref_items = session.get(cr_url, timeout=30).json()["message"]["items"]

def x_title(w):
    return (g(w, "title", 0) or g(w, "short-title", 0)
            or g(w, "container-title", 0) or "")

crossref_records = [
    {
        "title":  x_title(w),
        "author": author_str(w.get("author", [])),
        "year":   (g(w, "issued", "date-parts", 0, 0)
                   or g(w, "published-online", "date-parts", 0, 0)
                   or g(w, "created", "date-parts", 0, 0)),
        "journal": g(w, "container-title", 0) or w.get("publisher", ""),
        "doi":     w.get("DOI"),
        "href":    f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
    }
    for w in crossref_items
]

# ── 3. Merge (prefer Crossref) ─────────────────────────────────────────────
by_doi = {r["doi"].lower(): r for r in crossref_records if r.get("doi")}
merged = crossref_records.copy()

# ── 3. Merge: prefer Crossref; fill *all* blanks from ORCID and keep put-code
for r in orcid_records:
    doi_key = (r.get("doi") or "").lower()
    if doi_key and doi_key in by_doi:
        base = by_doi[doi_key]

        # keep the ORCID put-code so we can fetch authors later
        if r.get("put-code") and not base.get("put-code"):
            base["put-code"] = r["put-code"]

        # copy any missing fields, *including author*
        for fld in ("title", "year", "journal", "author"):
            if not base.get(fld):
                base[fld] = r.get(fld)
    else:
        merged.append(r)

# ── 4. Fetch full ORCID record when author still missing ───────────────────
need_authors = [m for m in merged if not m.get("author") and m.get("put-code")]

for m in need_authors:
    pc = m["put-code"]
    work_url = f"https://pub.orcid.org/v3.0/{ORCID_ID}/work/{pc}"
    w = session.get(work_url, headers={"Accept": "application/json"}, timeout=30).json()
    contribs = g(w, "contributors", "contributor") or []
    authors  = [
        {
            "given":  g(c, "credit-name", "value") or g(c, "contributor-name", "given-names", "value") or "",
            "family": g(c, "contributor-name", "family-name", "value") or "",
        }
        for c in contribs
    ]
    m["author"] = author_str(authors)
    time.sleep(0.1)   # ~10 req/s max for public ORCID

# ── 5. Clean up & write YAML ───────────────────────────────────────────────
for r in merged:
    r.pop("put-code", None)
merged.sort(key=lambda r: int(r["year"] or 0), reverse=True)

with out_yaml.open("w", encoding="utf-8") as f:
    yaml.dump(merged, f, allow_unicode=True, sort_keys=False)

print(f"Wrote {len(merged)} publications → {out_yaml}")
