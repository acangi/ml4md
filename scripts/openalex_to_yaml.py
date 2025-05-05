#!/usr/bin/env python3
"""
Fetch all public works linked to your ORCID from the OpenAlex API
and write them into data/publications.yml for Quarto’s listing page.
"""
import os, requests, yaml, textwrap, sys, pathlib

ORCID_ID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")

# OpenAlex returns up to 200 items per page; loop until 'next' is null
base = f"https://api.openalex.org/works?filter=author.orcid:{ORCID_ID}&per-page=200"
url  = base + "&cursor=*"

records, seen = [], set()

while url:
    page = requests.get(url, timeout=30).json()
    for w in page["results"]:
        # deduplicate via canonical OpenAlex ID
        if w["id"] in seen:
            continue
        seen.add(w["id"])

        authors = "; ".join(a["author"]["display_name"] for a in w["authorships"])

        pl   = w.get("primary_location") or {}
        src  = pl.get("source") or {}
        journal = src.get("display_name")

        rec = dict(
            title   = w["title"],
            author  = authors,
            year    = w["publication_year"],
            journal = journal,
            doi     = w.get("doi"),
            href    = f"https://doi.org/{w['doi']}" if w.get("doi") else w["id"],
        )
        records.append(rec)
    cursor = page.get("meta", {}).get("next_cursor")
    url = f"{base}&cursor={cursor}" if cursor else None

# newest → oldest
records.sort(key=lambda r: r["year"] or 0, reverse=True)

out = pathlib.Path("data/publications.yml")
out.parent.mkdir(exist_ok=True, parents=True)
yaml.safe_dump(records, out.open("w", encoding="utf-8"),
               allow_unicode=True, sort_keys=False)

print(f"Wrote {len(records)} records → {out}")
