#!/usr/bin/env python3
"""Create data/publications.yml by merging ORCID and Crossref results."""
import json, yaml, os, re, requests, sys, itertools
from pathlib import Path

ORCID_ID = os.environ.get("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL    = os.environ.get("CONTACT_EMAIL", "webmaster@example.org")  # polite pool

root = Path(__file__).parent.parent
data_dir = root / "data"
data_dir.mkdir(exist_ok=True)
out_yaml = data_dir / "publications.yml"

### 1 ───────── pull works from ORCID
orcid_url = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
orcid_json = requests.get(orcid_url, headers={"Accept": "application/json"}, timeout=30).json()

orcid_items = []
for w in orcid_json.get("group", []):
    summary = w["work-summary"][0]

    # basic fields
    rec = {
        "title":    summary["title"]["title"]["value"],
        "year":     summary.get("publication-date", {}).get("year", {}).get("value"),
        "journal":  summary.get("journal-title", {}).get("value"),
    }

    # authors aren’t included in the summary call; leave blank
    rec["author"] = ""

    # external-ids may include DOI, arXiv, ISBN, etc.
    for x in summary.get("external-ids", {}).get("external-id", []):
        if x["external-id-type"].lower() == "doi":
            doi = x["external-id-value"].lower()
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orcid_items.append(rec)

### 2 ───────── pull works from Crossref (covers only Crossref DOIs)
cr_url = f"https://api.crossref.org/works?filter=orcid:{ORCID_ID}&mailto={EMAIL}&rows=1000"
cr_items = []
for w in requests.get(cr_url, timeout=30).json()["message"]["items"]:
    cr_items.append(
        {
            "title":   w.get("title", [""])[0],
            "author":  "; ".join(f"{a.get('given','')} {a.get('family','')}".strip()
                                 for a in w.get("author", [])),
            "year":    w.get("issued", {}).get("date-parts", [[None]])[0][0],
            "journal": w.get("container-title", [""])[0] or w.get("publisher"),
            "doi":     w.get("DOI"),
            "href":    f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
        }
    )

### 3 ───────── merge (keep Crossref record if DOI overlaps, otherwise ORCID)
by_doi = {rec["doi"].lower(): rec for rec in cr_items if rec.get("doi")}
merged = cr_items.copy()

for rec in orcid_items:
    doi = rec.get("doi", "").lower()
    if doi and doi in by_doi:
        continue                 # already have richer Crossref metadata
    merged.append(rec)

# sort newest → oldest
merged.sort(key=lambda r: r.get("year") or 0, reverse=True)

yaml.dump(merged, out_yaml.open("w", encoding="utf-8"),
          allow_unicode=True, sort_keys=False)

print(f"Wrote {len(merged)} items to {out_yaml}")
