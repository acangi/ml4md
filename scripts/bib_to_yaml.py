#!/usr/bin/env python3
"""
Convert references.bib → data/publications.yml for Quarto table listings.

For each BibTeX entry the script writes:
  citation : inline cite-marker  "[@Key]"
  author   : "First Last; Second Author"
  year     : "2024"
  month    : "04"                (2-digit, if month present)
  title    : as in BibTeX
  journal  : as in BibTeX
  doi      : bare DOI (no https:// prefix)
  href     : https://doi.org/<doi>
"""

from pathlib import Path
import re, sys, yaml, bibtexparser
from calendar import month_abbr

# ── helper: map BibTeX month tokens → 2-digit string ──────────────────────
_month_map = {m.lower(): f"{i:02d}" for i, m in enumerate(month_abbr) if m}
_month_map.update({  # long names & numeric
    "january":"01","february":"02","march":"03","april":"04","may":"05",
    "june":"06","july":"07","august":"08","september":"09",
    "october":"10","november":"11","december":"12",
    "1":"01","2":"02","3":"03","4":"04","5":"05","6":"06",
    "7":"07","8":"08","9":"09","10":"10","11":"11","12":"12",
})

def month_to_mm(value: str|None) -> str|None:
    if not value:
        return None
    val = value.strip().lower().replace(".", "")
    return _month_map.get(val)

# ── helper: parse “Last, First and Second, Third” → “First Last; Third Second” ──
def format_authors(bib_authors: str) -> str:
    parts = [a.strip() for a in bib_authors.split(" and ")]
    formatted = []
    for p in parts:
        if "," in p:
            last, first = [s.strip() for s in p.split(",", 1)]
            formatted.append(f"{first} {last}")
        else:
            formatted.append(p)
    return "; ".join(formatted)

# ── main conversion ───────────────────────────────────────────────────────
BIB   = Path("publications.bib")
OUT   = Path("publications.yml")
OUT.parent.mkdir(parents=True, exist_ok=True)

if not BIB.exists():
    sys.exit("publications.bib not found.")

db = bibtexparser.load(BIB.open(encoding="utf-8"))
records = []

for entry in db.entries:
    key       = entry.get("ID") or re.sub(r"\\W+", "", entry["title"])[:30]
    authors   = format_authors(entry.get("author", ""))
    year      = entry.get("year")
    month     = month_to_mm(entry.get("month"))
    journal   = entry.get("journal") or entry.get("booktitle", "")
    doi_raw   = (entry.get("doi") or "").lower()
    doi       = re.sub(r"^https?://doi\\.org/", "", doi_raw)
    rec = {
        "citation": f"[@{key}]",
        "author"  : authors,
        "year"    : year,
        "month"   : month,
        "title"   : entry.get("title", "").strip("{}"),
        "journal" : journal,
    }
    if doi:
        rec["doi"]  = doi
        rec["href"] = f"https://doi.org/{doi}"
        rec["path"] = f"https://doi.org/{doi}"
    records.append(rec)

# newest → oldest
records.sort(key=lambda r: (r.get("year") or 0, r.get("month") or "00"), reverse=True)

yaml.safe_dump(records, OUT.open("w", encoding="utf-8"),
               allow_unicode=True, sort_keys=False)

print(f"Wrote {len(records)} entries → {OUT}")
