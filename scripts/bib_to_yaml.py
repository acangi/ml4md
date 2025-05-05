#!/usr/bin/env python3
"""Convert references.bib -> data/publications.yml for Quarto listing.

Usage:
    python scripts/bib_to_yaml.py
"""
import bibtexparser, yaml, os, re, datetime
from pathlib import Path

BIB = Path('references.bib')
OUT = Path('data/publications.yml')
OUT.parent.mkdir(parents=True, exist_ok=True)

with open(BIB, 'r', encoding='utf-8') as bibfile:
    db = bibtexparser.load(bibfile)

items = []
for entry in db.entries:
    item = {}
    item['title'] = entry.get('title', '').replace('{', '').replace('}', '')
    # authors separated by ' and '
    if 'author' in entry:
        authors = [a.strip() for a in re.split(r' and ', entry['author'])]
        item['author'] = '; '.join(authors)
    if 'year' in entry:
        item['year'] = int(entry['year'])
    if 'journal' in entry:
        item['journal'] = entry['journal']
    if 'booktitle' in entry:
        item['journal'] = entry['booktitle']
    if 'doi' in entry:
        item['doi'] = entry['doi']
        item['href'] = f"https://doi.org/{entry['doi']}"
    if 'url' in entry:
        item.setdefault('href', entry['url'])
    items.append(item)

# sort by year desc
items.sort(key=lambda x: x.get('year', 0), reverse=True)

with open(OUT, 'w', encoding='utf-8') as outf:
    yaml.dump(items, outf, sort_keys=False, allow_unicode=True)

print(f"Wrote {len(items)} items to {OUT}")
