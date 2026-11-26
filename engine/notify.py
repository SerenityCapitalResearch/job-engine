"""Phone alerts. Telegram is the main channel; ntfy.sh is an optional second one."""
from __future__ import annotations

import html
import os
import time

import requests


def _age(job) -> str:
    h = job.age_hours()
    if h is None:
        return ""
    return f" · {int(h * 60)}m ago" if h < 1 else (f" · {int(h)}h ago" if h < 48 else f" · {int(h / 24)}d ago")


def format_job(job, label: str) -> str:
    flags = "".join({"CONTRACT": " 💰CONTRACT", "REMOTE": " 🌍", "REGION-LIMITED": " ⚠️region"}.get(t, "")
                    for t in job.tags)
    e = html.escape
    return (f"<b>{e(job.title)}</b>{flags}\n{e(job.company)} · {e(job.location or 'n/a')}{_age(job)}\n"
            f"<i>{e(label)} · {e(job.source)}</i>\n"
            + (f"📄 Use: {e(job.resume)}\n" if job.resume else "") + f"{e(job.url)}")


def send_telegram(text: str) -> bool:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[no telegram configured]\n" + text + "\n")
        return False
    for _ in range(3):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20, data={
            "chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})
        if r.status_code == 429:  # flood control
            time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
            continue
        return r.ok
    return False


def send_ntfy(title: str, text: str, url: str = ""):
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        headers = {"Title": title.encode("ascii", "ignore").decode()}
        if url:
            headers["Click"] = url
        requests.post(f"https://ntfy.sh/{topic}", data=text.encode(), headers=headers, timeout=15)


def alert_jobs(jobs_with_labels, pause=1.1):
    sent = 0
    for job, label in jobs_with_labels:
        send_telegram(format_job(job, label))
        sent += 1
        time.sleep(pause)
    return sent
