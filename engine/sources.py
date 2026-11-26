"""Job fetchers. Every fetcher returns a list[Job] and raises on failure;
the runner catches errors per source so one broken site never stops the run."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from .models import Job, parse_dt

UA = {"User-Agent": "Mozilla/5.0 (personal job-alert script)"}
TIMEOUT = 25


def _get(url, **kw):
    r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def _post(url, **kw):
    r = requests.post(url, headers={**UA, **kw.pop("headers", {})}, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def _pretty(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


# --------------------------------------------------------------------------
# Employer applicant-tracking systems (earliest signal: jobs appear here first)
# --------------------------------------------------------------------------
def greenhouse(slug, **_):
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").json()
    out = []
    for j in data.get("jobs", []):
        out.append(Job("greenhouse", str(j["id"]), j.get("title", ""), _pretty(slug),
                       (j.get("location") or {}).get("name", ""), j.get("absolute_url", ""),
                       parse_dt(j.get("first_published") or j.get("updated_at"))))
    return out


def lever(slug, **_):
    data = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json").json()
    out = []
    for j in data:
        cat = j.get("categories") or {}
        wt = (j.get("workplaceType") or "").lower()
        out.append(Job("lever", j["id"], j.get("text", ""), _pretty(slug),
                       cat.get("location", "") or "", j.get("hostedUrl", ""),
                       parse_dt(j.get("createdAt")), employment=cat.get("commitment", "") or "",
                       remote=True if wt == "remote" else None))
    return out


def ashby(slug, **_):
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").json()
    out = []
    for j in data.get("jobs", []):
        out.append(Job("ashby", j["id"], j.get("title", ""), _pretty(slug),
                       j.get("location", "") or "", j.get("jobUrl", ""),
                       parse_dt(j.get("publishedAt")), employment=j.get("employmentType", "") or "",
                       remote=True if j.get("isRemote") else None))
    return out


def workable(slug, **_):
    data = _post(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
                 json={"query": "", "location": [], "department": [], "worktype": [], "remote": []}).json()
    out = []
    for j in data.get("results", []):
        loc = j.get("location") or {}
        place = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
        out.append(Job("workable", j["shortcode"], j.get("title", ""), _pretty(slug), place,
                       f"https://apply.workable.com/{slug}/j/{j['shortcode']}/",
                       parse_dt(j.get("published")), employment=j.get("type", "") or "",
                       remote=True if j.get("remote") else None))
    return out


def smartrecruiters(slug, **_):
    data = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100").json()
    out = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        place = ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x)
        out.append(Job("smartrecruiters", j["id"], j.get("name", ""),
                       (j.get("company") or {}).get("name", _pretty(slug)), place,
                       f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                       parse_dt(j.get("releasedDate")),
                       employment=(j.get("typeOfEmployment") or {}).get("label", ""),
                       remote=True if loc.get("remote") else None))
    return out


def _workday_posted(text: str):
    t = (text or "").lower()
    now = datetime.now(timezone.utc)
    if "today" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", t)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None


def workday(entry, queries=None, **_):
    """entry: {name, host, tenant, site}. Big employers (banks, telcos, insurers)."""
    host, tenant, site, name = entry["host"], entry["tenant"], entry["site"], entry.get("name", entry["tenant"])
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    seen, out = set(), []
    for q in (queries or [""]):
        data = _post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q}).json()
        for j in data.get("jobPostings", []):
            path = j.get("externalPath", "")
            if not path or path in seen:
                continue
            seen.add(path)
            out.append(Job("workday", f"{tenant}{path}", j.get("title", ""), name,
                           j.get("locationsText", "") or "",
                           f"https://{host}/en-US/{site}{path}", _workday_posted(j.get("postedOn", ""))))
    return out


# --------------------------------------------------------------------------
# Remote / global boards with free feeds
# --------------------------------------------------------------------------
def remoteok(**_):
    data = _get("https://remoteok.com/api").json()
    out = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue
        out.append(Job("remoteok", str(j["id"]), j["position"], j.get("company", ""),
                       j.get("location") or "Worldwide", j.get("url", ""),
                       parse_dt(j.get("epoch") or j.get("date")), remote=True))
    return out


def himalayas(pages=5, **_):
    out = []
    for p in range(pages):
        data = _get(f"https://himalayas.app/jobs/api?limit=20&offset={p * 20}").json()
        jobs = data.get("jobs", [])
        if not jobs:
            break
        for j in jobs:
            regions = j.get("locationRestrictions") or []
            loc = ", ".join(regions) if regions else "Worldwide"
            out.append(Job("himalayas", str(j.get("guid") or j.get("applicationLink") or j.get("title")),
                           j.get("title", ""), j.get("companyName", ""), loc,
                           j.get("applicationLink") or j.get("guid", ""),
                           parse_dt(j.get("pubDate")), employment=j.get("employmentType", "") or "",
                           remote=True))
    return out


def weworkremotely(feeds=None, **_):
    feeds = feeds or ["https://weworkremotely.com/remote-jobs.rss"]
    out = []
    for feed in feeds:
        root = ET.fromstring(_get(feed).content)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            company, _, role = title.partition(": ")
            if not role:
                company, role = "", title
            region = (it.findtext("region") or "Anywhere").strip()
            link = (it.findtext("link") or "").strip()
            out.append(Job("wwr", it.findtext("guid") or link, role, company, region, link,
                           parse_dt(it.findtext("pubDate")), remote=True,
                           employment=(it.findtext("type") or "")))
    return out


def remotive(**_):
    data = _get("https://remotive.com/api/remote-jobs").json()
    return [Job("remotive", str(j["id"]), j.get("title", ""), j.get("company_name", ""),
                j.get("candidate_required_location") or "Worldwide", j.get("url", ""),
                parse_dt(j.get("publication_date")), employment=j.get("job_type", "") or "",
                remote=True) for j in data.get("jobs", [])]


def jobicy(**_):
    data = _get("https://jobicy.com/api/v2/remote-jobs?count=50").json()
    out = []
    for j in data.get("jobs", []):
        jt = j.get("jobType")
        out.append(Job("jobicy", str(j["id"]), j.get("jobTitle", ""), j.get("companyName", ""),
                       j.get("jobGeo") or "Worldwide", j.get("url", ""), parse_dt(j.get("pubDate")),
                       employment=", ".join(jt) if isinstance(jt, list) else (jt or ""), remote=True))
    return out


def arbeitnow(**_):
    data = _get("https://www.arbeitnow.com/api/job-board-api").json()
    return [Job("arbeitnow", j["slug"], j.get("title", ""), j.get("company_name", ""),
                j.get("location", ""), j.get("url", ""), parse_dt(j.get("created_at")),
                employment=", ".join(j.get("job_types") or []),
                remote=True if j.get("remote") else None) for j in data.get("data", [])]


# --------------------------------------------------------------------------
# Search APIs (free keys) - best coverage for India, Canada and everywhere else
# --------------------------------------------------------------------------
def adzuna(countries, phrases, **_):
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise RuntimeError("ADZUNA_APP_ID / ADZUNA_APP_KEY not set (free key at developer.adzuna.com)")
    out = []
    for c in countries:
        for ph in phrases:
            data = _get(f"https://api.adzuna.com/v1/api/jobs/{c}/search/1", params={
                "app_id": app_id, "app_key": app_key, "results_per_page": 50,
                "what_phrase": ph, "sort_by": "date", "max_days_old": 3}).json()
            for j in data.get("results", []):
                out.append(Job(f"adzuna-{c}", str(j["id"]), j.get("title", ""),
                               (j.get("company") or {}).get("display_name", ""),
                               (j.get("location") or {}).get("display_name", ""),
                               j.get("redirect_url", ""), parse_dt(j.get("created")),
                               employment=" ".join(filter(None, [j.get("contract_type"), j.get("contract_time")]))))
    return out


def jooble(locations, phrases, **_):
    key = os.getenv("JOOBLE_API_KEY")
    if not key:
        raise RuntimeError("JOOBLE_API_KEY not set (free key at jooble.org/api/about)")
    out = []
    for loc in locations:
        for ph in phrases:
            data = _post(f"https://jooble.org/api/{key}", json={"keywords": ph, "location": loc}).json()
            for j in data.get("jobs", []):
                out.append(Job("jooble", str(j.get("id") or j.get("link")), j.get("title", ""),
                               j.get("company", ""), j.get("location", ""), j.get("link", ""),
                               parse_dt(j.get("updated")), employment=j.get("type", "") or ""))
    return out


# --------------------------------------------------------------------------
# Anything else: recruiter agencies, custom RSS feeds, plain career pages
# --------------------------------------------------------------------------
def rss(entry, **_):
    root = ET.fromstring(_get(entry["url"]).content)
    name = entry.get("name", "RSS")
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        out.append(Job(f"rss-{name}", it.findtext("guid") or link, (it.findtext("title") or "").strip(),
                       name, entry.get("location", ""), link, parse_dt(it.findtext("pubDate"))))
    for it in root.iter("{http://www.w3.org/2005/Atom}entry"):  # Atom feeds
        ns = "{http://www.w3.org/2005/Atom}"
        link_el = it.find(f"{ns}link")
        link = link_el.get("href", "") if link_el is not None else ""
        out.append(Job(f"rss-{name}", it.findtext(f"{ns}id") or link,
                       (it.findtext(f"{ns}title") or "").strip(), name, entry.get("location", ""), link,
                       parse_dt(it.findtext(f"{ns}updated"))))
    return out


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def page_links(entry, **_):
    """Watch a static career/agency page: every link whose text looks like a job title is a candidate.
    (Pages that build their list with JavaScript will return nothing - use their RSS/alerts instead.)"""
    html = _get(entry["url"]).text
    p = _Links()
    p.feed(html)
    name = entry.get("name", entry["url"])
    out, seen = [], set()
    for href, text in p.links:
        if not (6 <= len(text) <= 160) or not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        full = urljoin(entry["url"], href)
        if full in seen:
            continue
        seen.add(full)
        out.append(Job(f"page-{name}", full, text, name, entry.get("location", ""), full, None))
    return out
