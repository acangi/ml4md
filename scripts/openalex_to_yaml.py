#!/usr/bin/env python3
"""
Fetch all public works linked to your ORCID from the OpenAlex API
and write them into data/publications.yml for Quarto’s listing page.
"""
import os, requests, yaml, textwrap, sys, pathlib

#ORCID_ID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
ORCID_ID = "0000-0001-9162-262X"

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
        
        # --- classify ------------------------------------------------------------
        # OpenAlex uses a controlled vocabulary in w["type"]
        # • "journal-article"          → peer-reviewed paper
        # • "posted-content"           → preprint (arXiv, bioRxiv, ChemRxiv…)
        # • "proceedings-article"      → conference paper / talk abstract
        # • everything else            → leave as-is for now
        kind_map = {
            "article"   : "article",
            "report"   : "report",
            "book-chapter"      : "chapter",
            "book"              : "book",
            "preprint"    : "preprint",
            "proceedings-article": "talk",          # e.g. Bulletin of the APS
        }
        kind = kind_map.get(w["type"], w["type"])    # fall back to raw type

        # -------- safe journal lookup (can be None) ------------------------------
        pl   = w.get("primary_location") or {}
        src  = pl.get("source") or {}
        journal = src.get("display_name")

        # -------- assemble record -------------------------------------------------
        rec = dict(
            title   = w["title"],
            author  = authors,
            year    = w["publication_year"],
            date    = w["publication_date"],
            journal = journal,
            doi     = w.get("doi"),
            href    = f"https://doi.org/{w['doi']}" if w.get("doi") else w["id"],
            kind    = kind,                         # ← NEW TAG
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

# --- after the big records list is finished ------------------------------
articles = [r for r in records if r["kind"] == "article"]
preprints = [r for r in records if r["kind"] == "preprint"]
others = [r for r in records if r["kind"] != "paper"]

out_dir = pathlib.Path("data")
out_dir.mkdir(exist_ok=True, parents=True)

yaml.safe_dump(articles, (out_dir / "articles.yml").open("w", encoding="utf-8"),
               allow_unicode=True, sort_keys=False)
yaml.safe_dump(preprints, (out_dir / "preprints.yml").open("w", encoding="utf-8"),
               allow_unicode=True, sort_keys=False)
yaml.safe_dump(others, (out_dir / "others.yml").open("w", encoding="utf-8"),
               allow_unicode=True, sort_keys=False)

print(f"Wrote {len(articles)} peer-reviewed articles → data/papers.yml")
print(f"Wrote {len(preprints)} preprints → data/preprints.yml")
print(f"Wrote {len(others)} others → data/others.yml")
