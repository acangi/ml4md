#!/usr/bin/env python3
"""Create data/publications.yml by merging ORCID and Crossref records.

• Pulls EVERY public work from ORCID (so you keep items that don’t have Crossref DOIs)
• Pulls richer metadata from Crossref (titles, authors) when available
• Fills blanks (title, year, journal) in Crossref entries with ORCID data

Requires: requests, pyyaml
"""
from pathlib import Path
import os, sys, json, requests, yaml

# ── helpers ────────────────────────────────────────────────────────────────
def g(node, *path):
    """Safe nested .get(); returns None if any link is missing."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node

def author_str(cr_authors):
    return "; ".join(
        f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
        for a in cr_authors
    )

# ── config ─────────────────────────────────────────────────────────────────
ORCID_ID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL    = os.getenv("CONTACT_EMAIL", "webmaster@example.org")    # Crossref polite-pool

root      = Path(__file__).resolve().parent.parent
data_dir  = root / "data"
data_dir.mkdir(exist_ok=True, parents=True)
out_yaml  = data_dir / "publications.yml"

# ── 1. ORCID (all works, any DOI agency, or no DOI) ────────────────────────
orcid_url = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
orcid_json = requests.get(orcid_url, headers={"Accept": "application/json"}, timeout=30).json()

orcid_records = []
for grp in orcid_json.get("group", []):
    summary = grp["work-summary"][0]
    rec = {
        "title":   g(summary, "title", "title", "value") or "",
        "year":    g(summary, "publication-date", "year", "value"),
        "journal": g(summary, "journal-title", "value") or "",
        "author":  "",   # ORCID summary endpoint does not include authors
    }
    # find a DOI if present
    for xid in g(summary, "external-ids", "external-id") or []:
        if xid["external-id-type"].lower() == "doi":
            doi = xid["external-id-value"].lower()
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orcid_records.append(rec)

# ── 2. Crossref (only DOIs registered with Crossref) ───────────────────────
cr_url = f"https://api.crossref.org/works?filter=orcid:{ORCID_ID}&mailto={EMAIL}&rows=1000"
cr_items = requests.get(cr_url, timeout=30).json()["message"]["items"]

crossref_records = [
    {
        "title":  (g(w, "title", 0) or g(w, "short-title", 0) or g(w, "container-title", 0) or ""),
        "author": author_str(w.get("author", [])),
        "year":   (g(w, "issued",           "date-parts", 0, 0)
                   or g(w, "published-print",  "date-parts", 0, 0)
                   or g(w, "published-online", "date-parts", 0, 0)
                   or g(w, "created",          "date-parts", 0, 0)),
        "journal": g(w, "container-title", 0) or w.get("publisher", ""),
        "doi":     w.get("DOI"),
        "href":    f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
    }
    for w in cr_items
]

# ── 3. Merge: prefer Crossref; fill gaps from ORCID when DOI overlaps ──────
by_doi = {rec["doi"].lower(): rec for rec in crossref_records if rec.get("doi")}
merged = crossref_records.copy()

for rec in orcid_records:
    doi_key = (rec.get("doi") or "").lower()
    if doi_key and doi_key in by_doi:
        base = by_doi[doi_key]
        # patch missing fields
        for fld in ("title", "year", "journal", "author"):
            if not base.get(fld):
                base[fld] = rec.get(fld)
    else:
        merged.append(rec)

# ── 4. Sort newest → oldest and write YAML ─────────────────────────────────
merged.sort(key=lambda r: int(r["year"]) if r.get("year") else 0, reverse=True)

with out_yaml.open("w", encoding="utf-8") as f:
    yaml.dump(merged, f, allow_unicode=True, sort_keys=False)

print(f"Wrote {len(merged)} publications → {out_yaml}")
