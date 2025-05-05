#!/usr/bin/env python3
"""
Harvest publications for the Quarto site.

• ORCID summaries  ➜ basic metadata + put-codes
• Crossref         ➜ rich metadata when available
• If author list still blank, pull per-work BibTeX from ORCID and parse it
"""

from pathlib import Path
import os, sys, requests, yaml, time, bibtexparser, re

# ── helpers ────────────────────────────────────────────────────────────────
def g(node, *path):
    for key in path:
        if not isinstance(node, dict): return None
        node = node.get(key)
    return node

def author_string(names):
    return "; ".join(names)

def parse_bibtex_authors(tex: str) -> str:
    """Return 'Given Family; …' from a BibTeX record."""
    db = bibtexparser.loads(tex)
    if not db.entries: return ""
    names = db.entries[0].get("author", "")
    # Split on ' and ' then strip braces / commas
    parts = [re.sub(r"[{}]", "", p).strip() for p in names.split(" and ")]
    return author_string(parts)

# ── config ─────────────────────────────────────────────────────────────────
ORCID = os.getenv("ORCID_ID") or sys.exit("Missing ORCID_ID env var")
EMAIL = os.getenv("CONTACT_EMAIL", "webmaster@example.org")

root = Path(__file__).resolve().parent.parent
out = root / "data" / "publications.yml"
out.parent.mkdir(exist_ok=True, parents=True)

session = requests.Session()
session.headers.update(
    {"User-Agent": f"ml4md-publications/1.1 ({EMAIL})"})

# ── 1  ORCID summaries ────────────────────────────────────────────────────
summaries = session.get(
    f"https://pub.orcid.org/v3.0/{ORCID}/works",
    headers={"Accept": "application/json"}, timeout=30).json()

orc = []
for grp in summaries.get("group", []):
    s = grp["work-summary"][0]
    rec = {
        "put":     s["put-code"],
        "title":   g(s, "title", "title", "value") or "",
        "year":    g(s, "publication-date", "year", "value"),
        "journal": g(s, "journal-title", "value") or "",
        "author":  "",
    }
    for x in g(s, "external-ids", "external-id") or []:
        if x["external-id-type"].lower() == "doi":
            doi = x["external-id-value"].lower()
            rec["doi"]  = doi
            rec["href"] = f"https://doi.org/{doi}"
            break
    orc.append(rec)

# ── 2  Crossref works ──────────────────────────────────────────────────────
cr = session.get(
    f"https://api.crossref.org/works?filter=orcid:{ORCID}&rows=1000&mailto={EMAIL}",
    timeout=30).json()["message"]["items"]

cross = []
for w in cr:
    cross.append(
        {
            "title":  g(w, "title", 0) or g(w, "short-title", 0) or "",
            "author": "; ".join(f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
                                for a in w.get("author", [])),
            "year":   g(w, "issued", "date-parts", 0, 0)
                      or g(w, "published-online", "date-parts", 0, 0),
            "journal": g(w, "container-title", 0) or w.get("publisher", ""),
            "doi":     w.get("DOI"),
            "href":    f"https://doi.org/{w.get('DOI')}" if w.get("DOI") else None,
        }
    )
# ── 3-A  Bulk BibTeX → dict(doi → author list) ───────────────────────────
bib_url = f"https://pub.orcid.org/v3.0/{ORCID}/works?format=bibtex"
bib_tex = session.get(bib_url,
                      headers={"Accept": "application/x-bibtex"},
                      timeout=30).text

doi_to_authors = {}
for entry in bibtexparser.loads(bib_tex).entries:
    raw_doi = entry.get("doi") or entry.get("DOI") or ""
    doi     = raw_doi.lower().strip()
    authstr = re.sub(r"[{}]", "", entry.get("author", ""))
    names   = "; ".join([p.strip() for p in authstr.split(" and ") if p.strip()])
    if doi:
        doi_to_authors[doi] = names

# ── 3-B  Merge (prefer Crossref; keep put-code) ───────────────────────────
by_doi = {r["doi"].lower(): r for r in cross if r.get("doi")}
merged = cross.copy()

for r in orc:
    key = (r.get("doi") or "").lower()
    if key and key in by_doi:
        base = by_doi[key]
        if r.get("put") and not base.get("put"):
            base["put"] = r["put"]
        for f in ("title", "year", "journal", "author"):
            if not base.get(f):
                base[f] = r.get(f)
    else:
        merged.append(r)

# ── 4  Back-fill any blank or empty author from the BibTeX map ────────────
for m in merged:
    # treat None, '', or missing key as “no author”
    if not m.get("author"):
        doi_key = (m.get("doi") or "").lower()
        bib_auth = doi_to_authors.get(doi_key)
        if bib_auth:
            m["author"] = bib_auth

# ── 4-B  Last-chance per-work BibTeX (very few calls, only when STILL blank)
needs = [r for r in merged if not r.get("author") and r.get("put")]

for r in needs:
    work_bib = session.get(
        f"https://pub.orcid.org/v3.0/{ORCID}/work/{r['put']}/bibtex",
        headers={"Accept": "application/x-bibtex"}, timeout=30
    ).text
    parsed = parse_bibtex_authors(work_bib)
    if parsed:
        r["author"] = parsed
    time.sleep(0.2)          # ≤5 req/s → well under the public limit

# ── 5  Finalise & write YAML ───────────────────────────────────────────────
for r in merged:
    r.pop("put", None)
merged.sort(key=lambda r: int(r["year"] or 0), reverse=True)

yaml.dump(merged, out.open("w", encoding="utf-8"),
          allow_unicode=True, sort_keys=False)

print(f"✓  Wrote {len(merged)} publications → {out}")
