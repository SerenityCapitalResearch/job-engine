#!/usr/bin/env python3
"""Job engine: fetch every source, filter, de-duplicate, alert, and log.

  python run.py            normal run (what GitHub Actions calls every 30 min)
  python run.py --check    fetch everything, print per-source health, send nothing
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import yaml

from engine import notify, sources, store
from engine.filters import classify, is_contract, resolve

NOW = datetime.now(timezone.utc)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def load_companies():
    """companies.yaml (hand-written) merged with companies_found.yaml (written by discover.py)."""
    base, found = load("companies.yaml"), load("companies_found.yaml")
    for kind, items in found.items():
        merged = list(base.get(kind) or [])
        merged += [i for i in items if i not in merged]
        base[kind] = merged
    return base


def phrases_from(cfg, limit):
    """Search phrases for API sources: one title from each resume in turn, so every resume is covered."""
    return cfg["_phrases"][:limit]


def build_tasks(cfg, companies, state, force):
    """Returns [(name, callable)]. Throttled sources are skipped until their interval has passed."""
    tasks = []
    last = state.setdefault("last_run", {})

    def due(name, every):
        if force or not every:
            return True
        prev = last.get(name)
        return not prev or NOW - datetime.fromisoformat(prev) >= timedelta(minutes=every - 1)

    def add(name, fn, every=0):
        if due(name, every):
            tasks.append((name, fn, every))

    for kind in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters"):
        fetch = getattr(sources, kind)
        for slug in companies.get(kind) or []:
            add(f"{kind}:{slug}", lambda f=fetch, s=slug: f(s))

    queries = phrases_from(cfg, 6)
    for entry in companies.get("workday") or []:
        add(f"workday:{entry['name']}", lambda e=entry: sources.workday(e, queries=queries))
    for entry in companies.get("rss") or []:
        add(f"rss:{entry['name']}", lambda e=entry: sources.rss(e))
    for entry in companies.get("pages") or []:
        add(f"page:{entry['name']}", lambda e=entry: sources.page_links(e))

    b = cfg.get("boards") or {}
    if b.get("remoteok", {}).get("enabled"):
        add("board:remoteok", sources.remoteok, b["remoteok"].get("every_minutes", 30))
    if b.get("himalayas", {}).get("enabled"):
        add("board:himalayas", lambda: sources.himalayas(pages=b["himalayas"].get("pages", 5)),
            b["himalayas"].get("every_minutes", 30))
    if b.get("weworkremotely", {}).get("enabled"):
        add("board:weworkremotely", lambda: sources.weworkremotely(b["weworkremotely"].get("feeds")),
            b["weworkremotely"].get("every_minutes", 30))
    if b.get("remotive", {}).get("enabled"):
        add("board:remotive", sources.remotive, b["remotive"].get("every_minutes", 360))
    if b.get("jobicy", {}).get("enabled"):
        add("board:jobicy", sources.jobicy, b["jobicy"].get("every_minutes", 60))
    if b.get("arbeitnow", {}).get("enabled"):
        add("board:arbeitnow", sources.arbeitnow, b["arbeitnow"].get("every_minutes", 60))
    a = b.get("adzuna", {})
    if a.get("enabled"):
        ph = phrases_from(cfg, a.get("max_phrases", 6))
        add("board:adzuna", lambda: sources.adzuna(a["countries"], ph), a.get("every_minutes", 180))
    j = b.get("jooble", {})
    if j.get("enabled"):
        ph = phrases_from(cfg, j.get("max_phrases", 5))
        add("board:jooble", lambda: sources.jooble(j["locations"], ph), j.get("every_minutes", 180))
    return tasks


def run_task(t):
    name, fn, every = t
    try:
        return name, every, fn(), None
    except Exception as e:  # noqa: BLE001 - one broken site must never stop the run
        return name, every, [], f"{type(e).__name__}: {str(e)[:120]}"


def main():
    check = "--check" in sys.argv
    cfg, companies = resolve(load("config.yaml")), load_companies()
    state = store.load_state()
    first_run = not state["seen"]

    tasks = build_tasks(cfg, companies, state, force=check)
    with ThreadPoolExecutor(max_workers=cfg.get("workers", 16)) as ex:
        results = list(ex.map(run_task, tasks))

    health, jobs = {}, []
    for name, every, got, err in results:
        health[name] = (len(got), err)
        if not err and not check:
            state["last_run"][name] = NOW.isoformat()
        jobs.extend(got)

    labels = {s["id"]: s["label"] for s in cfg["sections"]}
    notify_sec = {s["id"]: s.get("alert", True) for s in cfg["sections"]}
    max_age = cfg.get("max_age_hours", 96)
    new, dup_fp = [], set()
    for job in jobs:
        if job.key in state["seen"]:
            continue
        age = job.age_hours()
        if age is not None and age > max_age:
            continue
        sec = classify(job, cfg)
        if not sec:
            continue
        if job.fingerprint in state["fingerprints"] or job.fingerprint in dup_fp:
            state["seen"][job.key] = NOW.isoformat()  # same job already seen via another source
            continue
        dup_fp.add(job.fingerprint)
        job.section = sec
        new.append(job)

    # contract first (you prefer it), then freshest first
    new.sort(key=lambda j: (not is_contract(j), -(j.posted.timestamp() if j.posted else 0)))
    cap = cfg.get("first_run_max_alerts", 60) if first_run else cfg.get("max_alerts_per_run", 80)
    to_alert = [j for j in new if notify_sec.get(j.section, True)][:cap]
    alerted = {j.key for j in to_alert}

    print(f"{len(tasks)} sources run, {len(jobs)} jobs fetched, {len(new)} new matches, {len(to_alert)} alerts")
    if check:
        for name, (n, err) in sorted(health.items()):
            print(f"  {'FAIL' if err else 'ok  '} {name:45s} {n:5d} {err or ''}")
        for j in new[:15]:
            print(f"  NEW [{j.section}] {j.title} | {j.company} | {j.location} | {j.url}")
        return

    notify.alert_jobs([(j, labels[j.section]) for j in to_alert])
    overflow = len([j for j in new if notify_sec.get(j.section, True)]) - len(to_alert)
    if overflow > 0:
        notify.send_telegram(f"ℹ️ {overflow} more matches not pushed to avoid flooding - "
                             f"see output/latest.md or jobs.csv in your repo.")

    for j in new:
        state["seen"][j.key] = NOW.isoformat()
        state["fingerprints"][j.fingerprint] = NOW.isoformat()
    store.append_csv([{
        "found_at": NOW.isoformat(timespec="minutes"), "section": j.section, "resume": j.resume, "tags": " ".join(j.tags),
        "title": j.title, "company": j.company, "location": j.location, "employment": j.employment,
        "posted": j.posted.isoformat(timespec="minutes") if j.posted else "", "source": j.source,
        "alerted": "yes" if j.key in alerted else "no", "url": j.url, "applied": "", "notes": ""} for j in new])
    store.write_latest_md(cfg["sections"])

    # once a day: tell the user which sources are broken, so silence never means "engine is dead"
    today = NOW.strftime("%Y-%m-%d")
    if state.get("last_health") != today:
        bad = [f"{n}: {e}" for n, (c, e) in health.items() if e]
        msg = f"✅ Job engine alive. {len(health)} sources checked today, {len(bad)} failing."
        if bad:
            msg += "\n" + "\n".join(bad[:15])
        notify.send_telegram(msg)
        state["last_health"] = today
    store.save_state(state)


if __name__ == "__main__":
    main()
