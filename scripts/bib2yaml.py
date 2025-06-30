# scripts/bib2yaml.py
import bibtexparser, yaml, datetime, re, pathlib

BIB = pathlib.Path(__file__).parent / ".." / "publications.bib"
YAML_OUT = pathlib.Path(__file__).with_name("pubitems.yaml")

def to_item(entry):
    # Basic fields; extend as required
    year  = entry.get("year", "1900")
    month = entry.get("month", "01").strip().lower()[:3]
    month_num = {
        'jan': '01','feb': '02','mar':'03','apr':'04','may':'05','jun':'06',
        'jul':'07','aug':'08','sep':'09','oct':'10','nov':'11','dec':'12'
    }.get(month, "01")
    item = {
        "title":   re.sub(r"[{}]", "", entry["title"]),
        "author":  entry.get("author","").replace("\n"," ").split(" and "),
        "date":    f"{year}-{month_num}-01",
        "path":    entry.get("url") or f"https://doi.org/{entry.get('doi','')}",
        # Optional extras:
        "categories": [entry.get("ENTRYTYPE")],
        "description": entry.get("abstract",""),
    }
    return item

db = bibtexparser.loads(BIB.read_text())
items = [to_item(e) for e in db.entries]

YAML_OUT.write_text(yaml.safe_dump(items, sort_keys=False, allow_unicode=True))
print(f"Wrote {len(items)} items -> {YAML_OUT}")
