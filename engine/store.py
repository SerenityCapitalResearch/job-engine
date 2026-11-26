"""State (what we've already seen) and the running tracker files you work from."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone

STATE_FILE = "state/seen.json"
CSV_FILE = "output/jobs.csv"
MD_FILE = "output/latest.md"
CSV_COLS = ["found_at", "section", "resume", "tags", "title", "company", "location", "employment", "posted", "source",
            "alerted", "url", "applied", "notes"]


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen": {}, "fingerprints": {}, "last_run": {}, "last_health": ""}


def save_state(state: dict, keep_days=60):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    for bucket in ("seen", "fingerprints"):
        state[bucket] = {k: v for k, v in state[bucket].items() if v >= cutoff}
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=0, sort_keys=True)


def append_csv(rows):
    os.makedirs("output", exist_ok=True)
    new = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def write_latest_md(sections, keep=400):
    """Rebuild a readable page of the most recent jobs per section from the CSV."""
    if not os.path.exists(CSV_FILE):
        return
    with open(CSV_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    labels = {s["id"]: s["label"] for s in sections}
    lines = [f"# Latest jobs (updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)\n"]
    for sid, label in labels.items():
        mine = [r for r in rows if r["section"] == sid][-keep:][::-1]
        lines.append(f"\n## {label} ({len(mine)})\n")
        for r in mine:
            tag = f" `{r['tags']}`" if r["tags"] else ""
            lines.append(f"- [{r['title']}]({r['url']}) - {r['company']} - {r['location']}{tag} - {r['resume']} "
                         f"({r['found_at'][:10]})")
    with open(MD_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
