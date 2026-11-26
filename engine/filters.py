"""Decides whether a job is relevant and which section of your feed it belongs to."""
from __future__ import annotations

import re

from .models import Job

INDIA = ["india", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "gurgaon", "gurugram", "noida",
         "hyderabad", "pune", "chennai", "kolkata", "ahmedabad", "kochi", "jaipur", "chandigarh", "indore",
         "thiruvananthapuram", "coimbatore", "navi mumbai", "thane"]
CANADA = ["canada", "toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary", "edmonton", "mississauga",
          "winnipeg", "quebec", "québec", "halifax", "victoria", "waterloo", "kitchener", "hamilton", "london, on",
          "markham", "burnaby", "surrey", "brampton", "regina", "saskatoon", "ontario", "british columbia",
          "alberta", "nova scotia", "manitoba"]
CANADA_CODES = re.compile(r",\s*(on|bc|ab|qc|ns|nb|mb|sk|nl|pe)\b", re.I)
REMOTE_WORDS = ["remote", "anywhere", "worldwide", "work from home", "wfh", "distributed", "global", "fully distributed"]
WORLDWIDE_OK = ["worldwide", "anywhere", "global", "international", "any location", "canada", "india", "apac",
                "asia", "north america", "americas"]
RESTRICTED = ["united states", "usa", "u.s.", "us only", "us-only", "europe", "emea", "uk", "united kingdom",
              "germany", "france", "netherlands", "spain", "ireland", "australia", "latam", "latin america",
              "brazil", "mexico", "singapore", "uae", "dubai", "israel", "poland", "portugal", "italy"]
CONTRACT_WORDS = ["contract", "contractor", "freelance", "temporary", "temp ", "fixed term", "fixed-term",
                  "c2c", "corp to corp", "consultant", "consulting", "interim", "short term", "short-term", "part-time contract"]


def _has(text: str, words) -> bool:
    t = text.lower()
    return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t) for w in words)


def title_matches(title: str, keywords) -> bool:
    if not keywords:
        return True
    t = title.lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(k.lower()), t) for k in keywords)


def is_remote(job: Job) -> bool:
    if job.remote:
        return True
    return _has(job.location, REMOTE_WORDS) or _has(job.title, ["remote", "work from home", "anywhere"])


def is_india(job: Job) -> bool:
    return _has(job.location, INDIA)


def is_canada(job: Job) -> bool:
    return _has(job.location, CANADA) or bool(CANADA_CODES.search(job.location))


def is_contract(job: Job) -> bool:
    return _has(f"{job.employment} {job.title}", CONTRACT_WORDS)


def region_limited(job: Job) -> bool:
    """Remote job that names specific countries but not 'worldwide' / Canada / India."""
    loc = job.location.lower()
    if not loc or _has(loc, WORLDWIDE_OK):
        return False
    return _has(loc, RESTRICTED)


def resolve(cfg: dict) -> dict:
    """Expands `titles: all_resumes` into the union of every non-India-only resume's titles, and builds
    a round-robin phrase list (one title from each resume in turn) for search-style APIs."""
    union = []
    for r in cfg.get("resumes", []):
        if r.get("india_only"):
            continue
        union += [t for t in r["titles"] if t not in union]
    for sec in cfg["sections"]:
        if sec.get("titles") == "all_resumes":
            sec["titles"] = union
    queues = [list(r["titles"]) for r in cfg.get("resumes", [])]
    phrases, seen = [], set()
    while any(queues):
        for q in queues:
            if q:
                t = q.pop(0)
                key = re.sub(r"[^a-z]+", "", t.lower())  # "go-to-market" == "go to market"
                if key not in seen:
                    seen.add(key)
                    phrases.append(t)
    cfg["_phrases"] = phrases
    return cfg


def pick_resume(job: Job, sec: dict, cfg: dict) -> str:
    if sec.get("resume"):
        return next((r["label"] for r in cfg["resumes"] if r["id"] == sec["resume"]), sec["resume"])
    for r in cfg.get("resumes", []):
        if r.get("india_only"):
            continue
        if title_matches(job.title, r["titles"]):
            return r["label"]
    return ""


def classify(job: Job, cfg: dict):
    """Returns the id of the first matching section, or None to drop the job."""
    if _has(job.title, cfg.get("exclude_titles", [])):
        return None
    remote, india, canada = is_remote(job), is_india(job), is_canada(job)
    for sec in cfg["sections"]:
        if not sec.get("enabled", True):
            continue
        where = sec.get("where", "any")
        ok = (where == "any" or (where == "india" and india) or (where == "canada" and canada)
              or (where == "remote" and remote))
        if ok and title_matches(job.title, sec.get("titles")):
            if is_contract(job):
                job.tags.append("CONTRACT")
            job.resume = pick_resume(job, sec, cfg)
            if remote:
                job.tags.append("REMOTE")
            if remote and region_limited(job):
                job.tags.append("REGION-LIMITED")
                if cfg.get("skip_region_limited", False) and where == "remote":
                    return None
            return sec["id"]
    return None
