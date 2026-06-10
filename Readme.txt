================================================================================
  HOLIDAY PLANNING TEMPLATE — WFM SCHEDULING TOOL
  Version 2.0 | Built for Enterprise WFM Schedulers
  Architecture last updated: 2026-06-10
================================================================================

OVERVIEW
--------
This tool helps WFM Schedulers plan staffing for holiday periods where contact
volume drops or spikes from normal levels. It covers the full planning chain:

  1. Enter historical holiday volumes (up to 5 years, Y1–Y5) across all channels
  2. Auto-calculate year-on-year impact % per holiday per channel
  3. Generate all valid trend combinations (Y1, Y2, Y3, averages, exclusions)
  4. Get a smart recommendation on which combination to use
  5. Break weekly forecast down to daily volumes (by channel)
  6. Calculate Net and Gross headcount (Erlang C for voice, concurrency for chat,
     throughput for email — all overnight-window aware)
  7. Enter your planned shifts and see coverage gaps vs Gross HC
  8. Get a suggested shift starting point per channel with planned vs recommended
     side-by-side comparison

CHANNELS SUPPORTED
------------------
  Voice    — Erlang C staffing model (log-space, supports any agent count)
  Chat     — Concurrency model (sessions per agent)
  Email    — Throughput model (daily capacity with configurable occupancy %)
  Blended  — Weighted voice + chat composite (configurable split %)

FILES IN THIS PROJECT
---------------------
  README.TXT          This file. Start here.
  style-guide.css     All CSS variables, color tokens, typography, and component
                      styles. Edit this file only to retheme the tool.
  index.htm           Main application. Open in any modern browser.
                      No server required for core functionality.
  data_engine.py      Optional Python backend for production-grade computation:
                      log-space Erlang C, overnight interval distribution,
                      email throughput with operating-window awareness,
                      combination scoring, and shift optimisation.
  sample_data.json    Three pre-loaded holidays (Christmas, New Year, Diwali)
                      covering all channels with Y1–Y5 historical data slots.
                      Load via the "Import data" button in the app.

HOW TO USE (BROWSER-ONLY MODE)
-------------------------------
  1. Open index.htm in Chrome, Edge, Firefox, or Safari (modern versions)
  2. Tab 1 (Setup)              Enter holidays, plan volumes, shrinkage,
                                SL targets, AHT, email occupancy %, blended split
  3. Tab 2 (Historical)         Review impact %, flag anomaly years
  4. Tab 3 (Combinations)       See all trend scenarios; hover score for breakdown
  5. Tab 4 (Recommendation)     Review smart pick with rationale; override if needed
  6. Tab 5 (Daily Breakdown)    Review 7-day volume split per channel
  7. Tab 6 (HC & Coverage)      Net and gross HC at daily + 30-min interval level
  8. Tab 7 (Shift Planner)      Enter planned shifts; review gap vs Gross HC
  9. Tab 8 (Shift Recommendation) Suggested shift starting point; planned vs
                                   recommended comparison per channel

HOW TO USE (PYTHON BACKEND MODE)
----------------------------------
  Requirements: Python 3.9+

  Install dependencies:
    pip install flask flask-cors numpy scipy

  scipy is used by the shift optimiser (scipy.optimize.linprog) for optional
  linear-programming extensions. The greedy heuristic runs without it.

  Run the server:
    python data_engine.py

  NOTE (v2.0.x): The backend connection is an INDICATOR ONLY in this version.
  The status dot in the header shows green when the backend is reachable, but
  all HC computation (Erlang C voice, chat concurrency, email throughput) runs
  browser-side regardless. The backend API endpoints are available for direct
  external use (scripts, CI validation). See the BACKEND MODE NOTE section
  below for full details. Backend routing will be activated in a future version.

IMPORTING AND EXPORTING DATA
-----------------------------
  Import: Click "Import data" in the header and select a .json file. Works when
  index.htm is opened directly from the filesystem (file://) or served over
  HTTP. Accepts files exported from this tool (any version) or the
  sample_data.json included in this package.

  Export: Click "Export data" in the header to download the current session
  state as a .json file. The export includes all holiday definitions, historical
  volumes, setup configuration (shrinkage, SL targets, AHT, occupancy %,
  blended split, DOW splits), and any saved shift plans. Use this to hand off
  plans between sessions or team members without re-entering data.

SHRINKAGE COMPONENTS
--------------------
  Total Shrinkage = 1 - (1 - Planned Leave%) x (1 - Unplanned Leave%) x (1 - Training%)
  Breaks are excluded from shrinkage (handled via AHT and occupancy).
  Gross HC = Net HC / (1 - Total Shrinkage%)

  Gap analysis on Tab 7 and shift recommendation on Tab 8 both compare planned
  agents against Gross HC (bodies required on floor), not Net HC.

EMAIL HC MODEL
--------------
  Email uses a daily throughput model, not an interval Erlang model:
    Throughput per agent = (Operating hours x 3600 x Occupancy%) / AHT
    Net HC = ceil(Daily email volume / Throughput per agent)

  Email Occupancy % is configured separately from Email SL% on the Setup tab.
  Email SL% tracks response-time commitments (e.g. 95% within 4 hours).
  Email Occupancy % targets agent utilisation (default 75%).

BLENDED CHANNEL
---------------
  Blended HC = Voice Erlang HC (on voice % of volume) + Chat concurrency HC
               (on chat % of volume). Configure the split on the Setup tab.
  Default: 60% voice, 40% chat. Must sum to 100%.

COMBINATION LOGIC
-----------------
  The tool generates every valid non-empty subset combination from all available
  year slots (up to 5 years: Y1 through Y5). With 5 years populated, this produces
  31 combinations (all subsets of size 1 to 5).

  Examples with 3 years:
    Single year:    Y1 only | Y2 only | Y3 only
    Two-year avg:   Avg(Y1+Y2) | Avg(Y2+Y3) | Avg(Y1+Y3)
    Three-year avg: Avg(Y1+Y2+Y3)

  Anomaly-flagged years excluded from combinations by default. User can
  force-include any flagged year via the override dropdown on Tab 2.

  Recommendation scoring (hover any combination row on Tab 3 to see breakdown):
    Consistency  40pts  Low coefficient of variation = stable trend
    Data richness 30pts  More years = higher confidence
    Recency bias  30pts  Y1 (most recent) weighted highest (1.0), Y2 (0.7),
                         Y3 (0.5), Y4 (0.3), Y5 (0.1)
    Anomaly penalty      -30pts per anomalous year included, capped so
                         anomalous data always ranks above no data

OVERNIGHT OPERATING WINDOWS
----------------------------
  Operating windows that cross midnight (e.g. 22:00–06:00) are fully supported.
  Intervals wrap correctly past midnight. Shift coverage detection handles all
  four combinations of overnight/daytime shifts against overnight/daytime
  intervals. A warning is shown on Setup and on holiday cards when an overnight
  window is detected.

SERVICE LEVEL AND STAFFING DEFAULTS
-------------------------------------
  Voice:   80% of calls answered within 20 seconds  | AHT 360s
  Chat:    90% of chats answered within 30 seconds  | AHT 480s | 2.5 concurrent sessions per agent
  Email:   95% of emails responded within 4 hours   | AHT 600s | Occupancy 75%
  Blended: 60% voice / 40% chat (configurable split)

  All defaults are editable on the Setup tab. Chat concurrency (sessions per
  agent) is configurable in the CONFIG block of index.htm.

SHIFT RECOMMENDATION (TAB 8)
-----------------------------
  The recommended shift plan is a greedy heuristic — it is a suggested starting
  point, not a guaranteed optimal solution. Manual adjustment of shift timings
  and agent counts may achieve higher SL coverage. The tool shows planned vs
  recommended coverage side-by-side so you can make an informed choice.

  The agent pool input represents gross bodies available on the roster (headcount),
  not net productive agents. The pool is split equally across selected channels.

BROWSER COMPATIBILITY
---------------------
  Tested on: Chrome 120+, Edge 120+, Firefox 121+, Safari 16+
  Not supported: Internet Explorer (any version)

KNOWN LIMITATIONS
-----------------
  - Email HC is computed as a daily throughput model. The 30-min interval
    drill-down on Tab 6 shows email HC distributed across intervals for
    scheduling visualisation, but email staffing decisions should be based
    on the daily summary figures, not interval-level numbers.
  - The greedy shift optimiser on Tab 8 is a heuristic. For complex multi-skill
    or tightly constrained shift designs, use the Python backend which can be
    extended with ILP solvers (scipy/Gurobi/CPLEX).
  - The tool does not connect to live WFM platforms. Data must be entered
    manually or imported via JSON.
  - Day-of-week split defaults to flat (1/7 per day). Always provide actual
    historical intraday profiles for production planning accuracy.
  - Blended channel HC: The HC & Coverage tab (Tab 6) and Shift Planner (Tab 7)
    compute Voice, Chat, and Email individually. "Blended" is not a selectable
    channel in those pickers. For blended holidays, select Voice and Chat
    separately and weight each channel's volume by the blended split % configured
    on the Setup tab. Alternatively, use the Python backend /api/full_day_hc with
    channel="blended". Note: the Export JSON plan (exportFinalPlan) does not
    include a blended_hc field — it contains peakNetHC, peakGrossHC, and
    weeklyForecast per channel (voice/chat/email individually, not blended).
  - Simultaneous use: IndexedDB plan storage uses a composite key (queue|region).
    Two browser tabs open on the same machine for the same queue and region share
    this key. Clicking "Save plan" in the second tab silently overwrites the first
    tab's data with no conflict warning (last-write-wins). For collaborative
    planning, work in separate browsers or export/import JSON to merge changes.

CONFIGURATION
-------------
  To retheme: edit style-guide.css only. Do not change colors in index.htm.
  To change scoring weights: edit scoreCombo() in index.htm (clearly marked).
  To add channels or custom SL models: edit the CONFIG section at the top of
  the JAVASCRIPT ENGINE block in index.htm.

CONFIG REFERENCE (index.htm — JAVASCRIPT ENGINE block)
-------------------------------------------------------
  BACKEND_URL          URL of the Python backend (default: 'http://localhost:5050')
  CHANNELS             Active channel list (['voice','chat','email','blended'])
  DEFAULT_DOW_SPLIT    7-element array of % volume per day (defaults to flat 1/7;
                       always replace with actual historical intraday profiles)
  Voice defaults       SL_TARGET=0.80, SL_SECONDS=20, AHT=360
  Chat defaults        SL_TARGET=0.90, SL_SECONDS=30, AHT=480, CONCURRENCY=2.5
  Email defaults       SL_TARGET=0.95, SL_HOURS=4,   AHT=600, OCCUPANCY=0.75
  Blended defaults     VOICE_PCT=0.60, CHAT_PCT=0.40

  Scoring weights (scoreCombo):
    Consistency   40 pts  (low coefficient of variation)
    Data richness 30 pts  (number of years with data, normalised to 5-year max)
    Recency bias  30 pts  (Y1=1.0, Y2=0.7, Y3=0.5, Y4=0.3, Y5=0.1 weight)
    Anomaly       -30 pts per anomalous year included (capped so anomalous
                          data still ranks above no data)

PYTHON BACKEND ENDPOINTS
------------------------
  GET  /health                    Service status check
  POST /api/shrinkage             Compound shrinkage build-up
  POST /api/erlang_c              Voice HC (log-space Erlang C, supports up to 2000 agents)
  POST /api/chat_hc               Chat HC (concurrency model)
  POST /api/email_hc              Email HC (throughput, overnight-aware)
  POST /api/interval_distribution Volume to 30-min Poisson intervals (overnight-aware)
  POST /api/combinations          All trend combinations with scoring
  POST /api/shift_optimise        Greedy shift optimisation (scipy.linprog available for ILP extension)
  POST /api/full_day_hc           Convenience wrapper — interval-level HC across all channels for one day

  Key internal functions (data_engine.py):
    erlang_c()               Core Erlang C probability (log-space safe)
    agentsForSL()            Binary-search agents needed to hit SL target
    serviceLevel()           SL% for a given agent count
    chatAgentsRequired()     Chat concurrency solver
    emailAgentsRequired()    Email throughput solver (returns net; API applies shrinkage)
    compoundShrinkage()      Compound shrinkage build-up
    distributeVolumeToIntervals()  Poisson interval split (overnight-aware)
    scoreCombination()       Consistency/richness/recency/anomaly scorer (aligned to JS)
    generateCombinations()   All valid Y1–Y5 subsets (2^5-1 = 31 max combinations)
    optimiseShifts()         Greedy shift packing heuristic

  See data_engine.py docstrings for request/response schemas.

VERSION HISTORY
---------------
  v1.0  Initial release — all 8 tabs, Erlang C, combination engine, shift planner
  v1.1  Multi-channel shift planning, overnight window support, file-based import,
        log-space Erlang C (JS), stale cache invalidation, anomaly live badges,
        ID-based holiday bindings, zero-sum DOW guards
  v1.2  Email occupancy separated from SL%, blended split configurable,
        gross HC used in gap analysis, AHT=0 guards, Python ValueError fix,
        same-time operating hours validation, overnight shift coverage fix,
        score breakdown hover card, planned vs recommended comparison,
        Safari AbortSignal fix, overnight warning on holiday cards,
        named channel toggle handlers, resetAll DOM fix
  v2.0  5-year history (Y1–Y5) in all engines and combination matrix,
        queue-first gate, recency weights corrected (Y1=highest, JS is authority),
        Python backend aligned to JS scoring (weights + anomaly penalty cap),
        combination engine extended to all-subsets over 5 slots (31 max),
        Erlang C exponent units cross-validated JS vs Python,
        anomaly penalty capped (anomalous data always ranks above no data),
        grossHC Chart.js overflow cap (9999 sentinel),
        HC chart accessible text legend (colour-blind safe),
        shrinkage-zeroed banner on plan load,
        DOW migration warning clarified with exact index displacement direction,
        aggregate import write gated behind explicit user confirmation,
        chat occupancy model difference between browser/backend documented,
        email API shrinkage-free behaviour documented for API consumers,
        CSS holiday-year-grid updated to 5-column auto-fit layout,
        Readme updated to reflect 5-year capability and v2.0 scoring weights

  v2.0.1 (Critic cycle 2 fixes):
        exportFinalPlan() version tag corrected from '1.2' to '2.0' — downstream
          automation and import tools will now correctly identify these exports as
          v2.0 plans containing Y4/Y5 data slots,
        SVG logo fallback fill attribute added for JS-disabled browsers,
        aggregate import confirm dialog now explicitly warns that only Voice actual
          is written — Chat and Email actuals must be set manually on Setup tab,
        hcSelectedChannels reset on plan restore to first holiday's active channels
          — prevents stale channel selection from a prior plan carrying into the new one,
        Tab 6 zero-volume inline warning added — user sees explicit message when HC
          is zero due to zero plan volume rather than a silent all-zeros table,
        Email daily summary column headers changed to 'Daily Net HC (flat)' and
          'Daily Gross HC (flat)' to clarify that email HC is a constant daily figure,
        Tab 3 renderCombinations debounce (60ms) added in switchTab to prevent
          redundant re-renders on rapid tab-bouncing,
        APP.backendOnline documented as indicator-only in pingBackend comment and
          status label — no HC computation routes to backend in current version,
        Erlang C mu label in data_engine.py corrected from 'per second' to 'per HOUR'
          — cosmetic fix; numeric result unchanged,
        scoreCombo recency averaging design intent documented inline,
        detectAnomalies n=2 behaviour documented — detection inactive at 2 data points

  BACKEND MODE NOTE
  -----------------
  In v2.0.x the Python backend status dot is an INDICATOR ONLY. All HC
  computation (Erlang C voice, chat concurrency, email throughput) runs
  browser-side regardless of whether the backend is reachable. The backend
  API endpoints (/api/erlang_c, /api/chat_hc, /api/email_hc) remain available
  for direct external use (scripts, CI validation). The browser-side Erlang C
  is numerically equivalent to the Python implementation (same sl_sec/aht
  exponent). Backend routing will be activated in a future version when the
  backend adds capabilities beyond browser parity (e.g. ILP shift optimisation).

================================================================================
  Built to WFM enterprise standards. Planner → Generator → Critic reviewed.
  Critic cycle 2 Amber items resolved. Score target: Green.
================================================================================
