#!/usr/bin/env python3
"""Convert Crossref “works” JSON → data/publications.yml"""
import json, yaml, sys, re, datetime, pathlib, textwrap

json_path  = pathlib.Path("works.json")
yaml_path  = pathlib.Path("data/publications.yml")
yaml_path.parent.mkdir(exist_ok=True, parents=True)

items = json.loads(json_path.read_text())["message"]["items"]

records = []
for w in items:
    rec = {
        "title":  w.get("title", [""])[0],
        "author": "; ".join(
            f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
            for a in w.get("author", [])
        ),
        "year":   w.get("issued", {}).get("date-parts", [[None]])[0][0],
        "journal": w.get("container-title", [""])[0] or w.get("publisher"),
        "doi":    w.get("DOI"),
        "href":   f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
    }
    records.append(rec)

# sort by year desc
records.sort(key=lambda r: r["year"] or 0, reverse=True)
yaml_path.write_text(yaml.dump(records, allow_unicode=True, sort_keys=False))
print(f"Wrote {len(records)} records → {yaml_path}")
