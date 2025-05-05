#!/usr/bin/env python3
"""Collect ORCID + Crossref; write data/publications.yml (safe for missing fields)."""
import json, yaml, os, requests, sys
from pathlib import Path

def g(node, *path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node

def author_str(authors):
    return "; ".join(f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
                     for a in authors)

ORCID_ID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL    = os.getenv("CONTACT_EMAIL", "webmaster@example.org")

root = Path(__file__).resolve().parent.parent
out  = root / "data" / "publications.yml"
out.parent.mkdir(exist_ok=True, parents=True)

# ── ORCID ────────────────────────────────────────────────────────────────
orcid_url = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
orcid_json = requests.get(orcid_url, headers={"Accept":"application/json"}, timeout=30).json()

orcid = []
for grp in orcid_json.get("group", []):
    s = grp["work-summary"][0]
    rec = {
        "title": g(s,"title","title","value") or "",
        "year":  (g(s,"publication-date","year","value") or
                  g(s,"created-date",     "year","value")),
        "journal": g(s,"journal-title","value") or "",
        "author": "",
    }
    for xid in g(s,"external-ids","external-id") or []:
        if xid["external-id-type"].lower() == "doi":
            doi = xid["external-id-value"].lower()
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orcid.append(rec)

# ── Crossref ─────────────────────────────────────────────────────────────
cross = []
url = f"https://api.crossref.org/works?filter=orcid:{ORCID_ID}&mailto={EMAIL}&rows=1000"
for w in requests.get(url, timeout=30).json()["message"]["items"]:
    title = (g(w,"title",0) or g(w,"short-title",0) or g(w,"original-title",0) or "")
    year  = (g(w,"issued","date-parts",0,0) or
             g(w,"published-online","date-parts",0,0) or
             g(w,"published-print","date-parts",0,0) or
             g(w,"created","date-parts",0,0))
    cross.append({
        "title": title,
        "author": author_str(w.get("author", [])),
        "year": year,
        "journal": g(w,"container-title",0) or w.get("publisher",""),
        "doi": w.get("DOI"),
        "href": f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
    })

# ── merge ────────────────────────────────────────────────────────────────
by_doi = {r["doi"].lower(): r for r in cross if r.get("doi")}
for r in orcid_recs:
    doi = (r.get("doi") or "").lower()
    if doi and doi in by_doi:
        base = by_doi[doi]
        # fill any blanks in Crossref record with ORCID data
        for field in ("title", "year", "journal", "author"):
            if not base.get(field):
                base[field] = r.get(field)
    else:
        merged.append(r)

yaml.dump(merged, out.open("w",encoding="utf-8"), allow_unicode=True, sort_keys=False)
print(f"Wrote {len(merged)} items to {out}")
