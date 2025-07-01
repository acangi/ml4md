#!/usr/bin/env python3
"""
Convert articles.yaml → references.bib for Quarto citeproc.
"""
import yaml
import re
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

# 1. Load your YAML
with open("../data/articles.yml") as f:
    records = yaml.safe_load(f)

db = BibDatabase()
entries = []
for rec in records:
    key = re.sub(r"\W+", "_", rec["title"])[:30]  # crude key
    entry = {
        "ID": key,
        "ENTRYTYPE": "article",
        "title": rec["title"],
        "author": rec["author"],
        "journal": rec.get("journal",""),
        "year": str(rec.get("year","")),
    }
    # strip off duplicate https://doi.org/ prefix if present
    doi = rec.get("doi","")
    if doi:
        doi = re.sub(r"^(https?://doi\.org/)+","", doi)
        entry["doi"] = doi
    entries.append(entry)

db.entries = entries
writer = BibTexWriter()
with open("references.bib","w") as bibfile:
    bibfile.write(writer.write(db))

print(f"Wrote {len(entries)} entries → references.bib")
