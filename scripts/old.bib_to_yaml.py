#!/usr/bin/env python3
"""
Convert references.bib → data/publications.yml for Quarto listings with CSL support.
"""
import re
from pathlib import Path
import bibtexparser
import yaml

# Paths
BIB_PATH = Path("../publications.bib")
OUT_DIR  = Path("../")
OUT_FILE = OUT_DIR / "publications.yml"

# Load BibTeX
if not BIB_PATH.exists():
    print(f"Error: {BIB_PATH} not found.")
    exit(1)

with BIB_PATH.open(encoding="utf-8") as bibfile:
    bib_db = bibtexparser.load(bibfile)

records = []
for entry in bib_db.entries:
    # Generate a citation key (falls back to ID)
    raw_id = entry.get("ID", "")
    key = re.sub(r"\W+", "", raw_id)
    # Build the inline citation marker
    citation = f"[@{key}]"

    rec = {
        "citation": citation,
        "year":     entry.get("year", ""),
        "title":    entry.get("title", "").replace("{", "").replace("}", ""),
        "journal":  entry.get("journal", ""),
    }
    records.append(rec)

# Ensure output directory exists
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Write YAML
with OUT_FILE.open("w", encoding="utf-8") as outfile:
    yaml.safe_dump(records, outfile, allow_unicode=True, sort_keys=False)

print(f"Wrote {len(records)} records → {OUT_FILE}")
