#!/usr/bin/env python3
"""Find which hiring system each company uses.

  python discover.py names.txt        (one company name per line)

Tries likely URL slugs on Greenhouse, Lever, Ashby, Workable and SmartRecruiters and saves
every hit to companies_found.yaml, which the engine reads automatically.
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
import yaml

H = {"User-Agent": "Mozilla/5.0 (personal job-alert script)"}


def variants(name):
    base = re.sub(r"\b(inc|ltd|llc|corp|corporation|limited|plc|group|co)\b\.?", "", name.lower()).strip()
    words = re.findall(r"[a-z0-9]+", base)
    cands = {"".join(words), "-".join(words), "_".join(words)}
    if len(words) > 1:
        cands.add(words[0])
    return [c for c in cands if c]


def probe(kind, slug):
    try:
        if kind == "greenhouse":
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", headers=H, timeout=15)
            return r.ok and bool(r.json().get("jobs"))
        if kind == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=H, timeout=15)
            return r.ok and isinstance(r.json(), list) and len(r.json()) > 0
        if kind == "ashby":
            r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", headers=H, timeout=15)
            return r.ok and bool(r.json().get("jobs"))
        if kind == "workable":
            r = requests.post(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", headers=H, timeout=15,
                              json={"query": "", "location": [], "department": [], "worktype": [], "remote": []})
            return r.ok and bool(r.json().get("results"))
        if kind == "smartrecruiters":
            r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", headers=H, timeout=15)
            return r.ok and r.json().get("totalFound", 0) > 0
    except Exception:
        return False
    return False


def main(path):
    names = [n.strip() for n in open(path, encoding="utf-8") if n.strip() and not n.startswith("#")]
    jobs = [(k, s, n) for n in names for s in variants(n)
            for k in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters")]
    with ThreadPoolExecutor(max_workers=12) as ex:
        hits = list(ex.map(lambda t: (t, probe(t[0], t[1])), jobs))
    found, matched = {}, set()
    for (kind, slug, name), ok in hits:
        if ok:
            found.setdefault(kind, set()).add(slug)
            matched.add(name)
            print(f"found  {name:30s} -> {kind}: {slug}")
    for n in names:
        if n not in matched:
            print(f"none   {n}  (probably a custom careers site or Workday - add it by hand)")
    try:
        existing = yaml.safe_load(open("companies_found.yaml")) or {}
    except FileNotFoundError:
        existing = {}
    for kind, slugs in found.items():
        existing[kind] = sorted(set(existing.get(kind, [])) | slugs)
    with open("companies_found.yaml", "w") as f:
        yaml.safe_dump(existing, f)
    print("\nSaved to companies_found.yaml")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
