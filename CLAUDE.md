# Holiday Planning WFM Tool — Project Guide

## Project Identity

Browser-based Workforce Management scheduling tool for planning staffing across holiday periods. Single-page application with an optional Python backend.

**Live site:** https://ranjan-003.github.io/holiday-planning/
**GitHub repo:** https://github.com/Ranjan-003/holiday-planning

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML / CSS / JavaScript — single file (`index.htm`, ~2100 lines) |
| Styling | CSS custom properties in `style-guide.css` — never embed colors in `index.htm` |
| Charts | Chart.js 4.4.1 (CDN) |
| Spreadsheet | SheetJS xlsx-0.20.3 (CDN) |
| Fonts | Inter (UI) + JetBrains Mono (data values) — Google Fonts CDN |
| Backend (optional) | Python 3.9+ Flask server (`data_engine.py`) on port 5050 |

No build step. No framework. Open `index.htm` directly in any modern browser.

## Key Files

| File | Purpose |
|---|---|
| `index.htm` | Main application — all 8 tabs, all logic, all UI. Edit with care. |
| `style-guide.css` | All CSS variables and component styles. Retheme here only. |
| `data_engine.py` | Optional Python backend: Erlang C, shift optimiser, overnight intervals. |
| `sample_data.json` | Pre-loaded demo data (Christmas, New Year, Diwali — all channels). |
| `Readme.txt` | Full usage guide, formula documentation, config reference. |

## WFM Domain Constraints

These rules are non-negotiable. Any output that violates them is incorrect.

- **HC vs FTE** — Always distinct. Never conflate headcount (bodies scheduled) with FTEs (annualised equivalents).
- **Shrinkage** — Always compound: `1 − (1−Planned%) × (1−Unplanned%) × (1−Training%)`. Never a single blended figure.
- **Erlang C** — Voice channel only. Chat uses the concurrency model (sessions per agent). Email uses daily throughput (operating hours × occupancy / AHT).
- **Gross HC** — Used in all gap analysis and shift recommendation (bodies required on floor). Net HC is the pre-shrinkage requirement.
- **CSS tokens** — All colors must come from CSS variables in `style-guide.css`. No hardcoded hex values in `index.htm`.
- **No placeholders** — Every formula, calculation, and UI component must be complete and runnable. No TODOs. No stubs.

## Channels

| Channel | Staffing Model |
|---|---|
| Voice | Erlang C (log-space, up to 2000 agents) |
| Chat | Concurrency (sessions per agent, default 2.5) |
| Email | Daily throughput (operating window × occupancy / AHT) |
| Blended | Weighted Voice + Chat (configurable split, default 60/40) |

## Year Slots

Y1 = most recent year (Last Year), Y2 = one year prior, ..., Y5 = four years prior. Labels are dynamic based on detected or configured base year.

## Queue Context

Queues belong to a region (APJ / EMEA / AMER / LATAM) and a type (DB = internal, OSP = external). Queue context is set in the bar above the tabs.

---

## MANDATORY RULE — ALL CODE CHANGES

**You must never make direct file edits when asked to implement a feature or fix.**

Every code change request — no matter how small — must go through the three-agent quality pipeline by running the `/implement` slash command:

```
/implement <description of what you want built or fixed>
```

The pipeline will run automatically (maximum **2 generate→critique cycles**):

1. **wfm-planner** — decomposes the request into a numbered sub-task checklist with inputs, success criteria, and WFM constraints. Must be specific enough that the generator can execute without ambiguity.
2. **wfm-generator** — implements every sub-task with full file access; reads before writing; builds completely. On cycle 2, receives the full cycle-1 critique and must resolve every item.
3. **wfm-critic** — reads the changed files and scores **Red / Amber / Green** against what was changed in this request only. Scoring rules:
   - **Green** — all WFM formulas correct, no false user-facing claims, no broken channel routing. Dead CSS rules, audit-trail gaps, and comment style do **not** block Green.
   - **Amber** — incorrect HC formula result, false UI claim, broken channel routing, or data-loss risk.
   - **Red** — runtime crash, Infinity/NaN in output, or direct WFM domain rule violation.
4. **Ship** — only on **Green**: `git add`, `git commit`, `git push` to GitHub. GitHub Pages redeploys automatically.

If the critic scores Amber or Red after both cycles, the pipeline surfaces the blocking questions. Address them and re-run `/implement` with an updated description.

**Do not bypass this pipeline by editing files directly. Do not commit before a Green score.**
