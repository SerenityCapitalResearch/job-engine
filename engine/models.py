from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


@dataclass
class Job:
    source: str
    job_id: str
    title: str
    company: str
    location: str
    url: str
    posted: Optional[datetime] = None
    employment: str = ""          # raw employment type text, e.g. "Contract", "Full-time"
    remote: Optional[bool] = None  # None = unknown
    section: str = ""              # filled in by the classifier
    resume: str = ""               # which of your resumes to send, filled in by the classifier
    tags: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.job_id}"

    @property
    def fingerprint(self) -> str:
        """Cross-source duplicate detector (same job seen on Adzuna and Greenhouse)."""
        raw = "|".join(norm(x) for x in (self.company, self.title, self.location))
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def age_hours(self) -> Optional[float]:
        if not self.posted:
            return None
        return (datetime.now(timezone.utc) - self.posted).total_seconds() / 3600


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def parse_dt(value) -> Optional[datetime]:
    """Accepts ISO strings, RFC822 strings, epoch seconds or epoch milliseconds."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            v = float(value)
            if v > 1e11:  # milliseconds
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        s = str(value).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
