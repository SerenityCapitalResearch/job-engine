# Job Engine

Checks hiring systems, remote boards and job-search APIs every 30 minutes, filters by your roles,
removes duplicates, and pings your phone the moment a new match appears. Free to run.

Four sections, in this order: **India · Equity Research**, **India · Other**, **Canada**, **Remote / Global**
(plus an optional silent "onsite elsewhere" bucket). Contract roles are tagged 💰 and pushed first.

Every match is also saved to `output/jobs.csv` (a tracker with `applied` and `notes` columns) and
`output/latest.md` (clickable list by section), so nothing is lost even on a 100-jobs-a-day day.

## Your five resumes

`config.yaml` has one set of job titles per resume (Go-to-Market, Project/Program, Lifecycle/Retention,
Decision Support/Procurement, and Equity Research for India). Every alert ends with **📄 Use: Resume N**,
and `output/jobs.csv` records it. Equity research roles are matched in India only.

`profile/fact_sheet.md` holds your agreed titles, dates and currency rules, so every resume and cover
letter says the same thing. Resolve the SBI Card figures marked OPEN there before you apply.

## Your Word resume format

`resume/template.docx` is your own Word file; `resume/build_resume.py` rebuilds a resume in exactly that
layout from a plain-text content file (`resume/content/india_gtm.yaml` is the first one):

    pip install python-docx pyyaml
    python resume/build_resume.py resume/content/india_gtm.yaml my_resume.docx

To tailor a resume for a job, copy the content file, edit the words, and run the command again.
Ask Claude to do the tailoring: paste the job description and it returns a ready .docx.

## Setup (about 20 minutes, one time)

**1. Telegram bot (your phone alerts)**
- In Telegram, message **@BotFather**, send `/newbot`, follow the prompts, copy the **token**.
- Open a chat with your new bot and send it any message.
- Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy the number after `"chat":{"id":`.

**2. Free job-search API keys (this is what gives you India and Canada coverage)**
- Adzuna: https://developer.adzuna.com → register → copy **App ID** and **App Key**.
- Jooble: https://jooble.org/api/about → request a key (arrives by email).
- Skipping either is fine; the engine just reports that source as "not configured".

**3. GitHub**
- Create a free GitHub account → **New repository**. Choose **Public** (unlimited free run-minutes; the repo
  holds only job listings and no personal data, your keys stay secret). If you choose Private, change the
  schedule in `.github/workflows/jobs.yml` from `*/30` to `0 * * * *` to stay inside the free minutes.
- Upload everything in this folder (drag and drop works, include the hidden `.github` folder).
- Repo → **Settings → Secrets and variables → Actions → New repository secret**. Add:
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `JOOBLE_API_KEY`
  (optional: `NTFY_TOPIC`).
- Repo → **Actions** tab → enable workflows → **job-engine** → **Run workflow**.

The first run finds a backlog and pushes the freshest 60; the rest wait in `output/latest.md`.

## Make it yours

1. **`config.yaml`** - replace the role keywords (the top of the file) with your real target titles.
   Titles are matched as "contains", so `data analyst` also catches `Senior Data Analyst - Remote`.
2. **`companies.yaml`** - this is what scales your coverage.
   Put company names in a text file and run `python discover.py names.txt`: it finds which hiring system each
   one uses and saves them to `companies_found.yaml`. Do it for banks, funds, research houses, startups,
   consultancies, anyone you'd work for.
3. **Test any change** locally with `python run.py --check` (prints which sources work and sample matches,
   sends nothing). Install first: `pip install -r requirements.txt`.

## Recruiting agencies

Agencies get you to interviews, but most hide their roles behind JavaScript search pages.
- Add any agency page with plain job links under `pages:` in `companies.yaml` (examples included).
- For agencies where that finds nothing, register on their site and switch on **their own email alerts**:
  Robert Half, Randstad, Hays, Michael Page, Adecco, TEKsystems, Insight Global, Procom, Altis, Kforce
  (Canada) and Naukri, Michael Page India, Randstad India, ABC Consultants, Kelly (India).
- Email the recruiters directly too, with your resume and target roles. Agencies often fill roles before posting.

## Sources that cannot be scraped (use their alerts, set once)

LinkedIn, Indeed, Glassdoor, Wellfound, Naukri, Foundit, Hiring Cafe: they block bots and some forbid scraping.
Set saved searches with **instant** email/push alerts. These are slower than the engine, so treat them as the safety net.

## Things to know

- Scheduled GitHub runs can lag by a few minutes, and GitHub pauses schedules in repos with no activity for
  60 days. The engine's own commits normally keep it alive; if it ever stops, click **Run workflow**.
- Once a day you get a "✅ engine alive" message listing any broken sources. Silence never means failure.
- "⚠️region" on a remote job means it names specific countries (e.g. "US only"). Check eligibility before applying.
- Apply with a tailored resume and cover letter per job. Bulk-submitting generic applications gets filtered out.
