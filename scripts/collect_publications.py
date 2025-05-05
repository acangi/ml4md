#!/usr/bin/env python3
"""Create data/publications.yml by merging ORCID and Crossref records."""
import json, yaml, os, re, requests, sys
from pathlib import Path

# ── helpers ────────────────────────────────────────────────────────────────
def g(node, *path):
    """Safe nested .get() that returns None if any link is missing."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node

def author_str(crossref_authors):
    return "; ".join(
        f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
        for a in crossref_authors
    )

# ── config ─────────────────────────────────────────────────────────────────
ORCID_ID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL    = os.getenv("CONTACT_EMAIL", "webmaster@example.org")    # polite-pool

root      = Path(__file__).resolve().parent.parent
data_dir  = root / "data"
data_dir.mkdir(exist_ok=True, parents=True)
out_yaml  = data_dir / "publications.yml"

# ── 1. ORCID works (all visibility = public) ───────────────────────────────
orcid_url  = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
orcid_json = requests.get(
    orcid_url,
    headers={"Accept": "application/json"},
    timeout=30
).json()

orcid_recs = []
for grp in orcid_json.get("group", []):
    summary = grp["work-summary"][0]        # each group has at least 1 summary
    rec = {
        "title":   g(summary, "title", "title", "value") or "",
        "year":    g(summary, "publication-date", "year", "value"),
        "journal": g(summary, "journal-title", "value") or "",
        "author":  "",                       # ORCID summary call lacks authors
    }

    # external IDs may include DOI, ISBN, arXiv …
    for xid in g(summary, "external-ids", "external-id") or []:
        if xid["external-id-type"].lower() == "doi":
            doi = xid["external-id-value"].lower()
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orcid_recs.append(rec)

# ── 2. Crossref works (only Crossref-registered DOIs) ──────────────────────
cr_url   = f"https://api.crossref.org/works?filter=orcid:{ORCID_ID}&mailto={EMAIL}&rows=1000"
cr_items = requests.get(cr_url, timeout=30).json()["message"]["items"]

crossref_recs = [
    {
        "title":   g(w, "title", 0) or "",
        "author":  author_str(w.get("author", [])),
        "year":    g(w, "issued", "date-parts", 0, 0),
        "journal": g(w, "container-title", 0) or w.get("publisher", ""),
        "doi":     w.get("DOI"),
        "href":    f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
    }
    for w in cr_items
]

# ── 3. Merge: prefer Crossref when DOI overlaps ────────────────────────────
by_doi = {r["doi"].lower(): r for r in crossref_recs if r.get("doi")}
merged = crossref_recs.copy()

for r in orcid_recs:
    doi = (r.get("doi") or "").lower()
    if doi and doi in by_doi:
        continue          # richer Crossref record already covers it
    merged.append(r)

# ── 4. Sort & write YAML ───────────────────────────────────────────────────
merged.sort(key=lambda r: int(r["year"]) if r.get("year") else 0, reverse=True)

yaml.dump(merged, out_yaml.open("w", encoding="utf-8"),
          allow_unicode=True, sort_keys=False)

print(f"Wrote {len(merged)} items → {out_yaml}")
