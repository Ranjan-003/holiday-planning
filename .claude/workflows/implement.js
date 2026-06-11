export const meta = {
  name: 'implement',
  description: 'WFM pipeline: wfm-planner plan, wfm-generator build, wfm-critic review, git push if Green',
  phases: [
    { title: 'Plan',     detail: 'wfm-planner decomposes the request into sub-tasks' },
    { title: 'Generate', detail: 'wfm-generator implements sub-tasks with file access' },
    { title: 'Critique', detail: 'wfm-critic reviews across 6 dimensions (Red/Amber/Green)' },
    { title: 'Ship',     detail: 'git commit and push only if critic score is Green' }
  ]
}

/* ── Project context block (static — injected into every agent prompt) ── */
const PROJECT_CONTEXT = `
PROJECT: Holiday Planning WFM Tool v2.0
PATH: C:\\Users\\ranjan.prasad\\Downloads\\holiday-planning
LIVE URL: https://ranjan-003.github.io/holiday-planning/
GITHUB: https://github.com/Ranjan-003/holiday-planning

KEY FILES:
  index.htm        Main app (~2100 lines). All 8 tabs, all JS logic, all UI.
  style-guide.css  All CSS variables. Retheme here only — no hex in index.htm.
  data_engine.py   Optional Python backend (Erlang C, shift optimiser).
  sample_data.json Pre-loaded demo data (Christmas, New Year, Diwali).
  Readme.txt       Full usage guide, formula docs, config reference.

TECH STACK: Vanilla HTML/CSS/JS (no build step). Chart.js 4.4.1 + SheetJS xlsx-0.20.3 (CDN).

WFM DOMAIN RULES (non-negotiable):
  - HC and FTE are always distinct — never conflated.
  - Shrinkage is always compound: 1 - (1-Planned%) x (1-Unplanned%) x (1-Training%).
  - Erlang C is used for Voice only. Chat = concurrency model. Email = daily throughput.
  - Gross HC is used in gap analysis and shift recommendation (bodies on floor, not net).
  - All CSS colors must use tokens from style-guide.css — no hardcoded hex in index.htm.
  - All code must be complete and runnable. No TODOs. No stubs. No placeholders.
  - Year slots: Y1 = most recent (Last Year), Y2, Y3, Y4, Y5 in descending order.
  - Channels: Voice | Chat | Email | Blended.
`

/* ── Structured output schema for the critic ── */
const CRITIC_SCHEMA = {
  type: 'object',
  properties: {
    score: {
      type: 'string',
      enum: ['Red', 'Amber', 'Green'],
      description: 'Overall critique verdict'
    },
    questions: {
      type: 'array',
      items: { type: 'string' },
      description: 'Specific questions or risks found during review'
    },
    summary: {
      type: 'string',
      description: 'One-sentence justification for the score'
    }
  },
  required: ['score', 'questions', 'summary']
}

const request = typeof args === 'string' ? args : JSON.stringify(args)

/* ════════════════════════════════════════════════════════════════
   PHASE 1 — PLAN
   wfm-planner receives project context + user request.
   Returns a numbered sub-task breakdown (no file access needed).
════════════════════════════════════════════════════════════════ */
phase('Plan')
log('Invoking wfm-planner to decompose the request into sub-tasks...')

const plan = await agent(
  `${PROJECT_CONTEXT}

USER REQUEST:
${request}

Decompose this request into numbered sub-tasks following your standard output format.
For each sub-task specify: what file(s) change, what WFM domain constraints apply,
inputs required, and success criteria. Flag any ambiguities before proceeding.`,
  {
    agentType: 'wfm-planner',
    label: 'wfm-planner',
    phase: 'Plan'
  }
)

log('Plan complete.')

/* ════════════════════════════════════════════════════════════════
   PHASES 2+3 — GENERATE → CRITIQUE LOOP (max 2 cycles)
   Each cycle: generator implements, critic reviews.
   On cycle 2, generator receives the full cycle-1 critique and
   MUST resolve every blocking item before returning.
   Loop exits early on Green.

   CRITIC SCORING RULES (enforced in prompt):
   - Score GREEN when all WFM formulas are correct and no user-
     facing information is false. Audit-trail gaps, dead CSS rules,
     and minor comment inconsistencies do NOT block Green.
   - Score AMBER only for: incorrect HC formula, false UI claim,
     broken channel routing, or data-loss risk.
   - Score RED only for: runtime crash, Infinity/NaN in output,
     or a calculation that violates WFM domain rules.
════════════════════════════════════════════════════════════════ */
let critique = null
let genResult = ''
const MAX_CYCLES = 2

for (let cycle = 1; cycle <= MAX_CYCLES; cycle++) {

  /* ── Generate ── */
  phase(`Generate — cycle ${cycle}`)
  log(`Invoking wfm-generator (cycle ${cycle} of ${MAX_CYCLES})...`)

  const prevCritiqueNote = critique
    ? `\n\nPREVIOUS CRITIQUE (cycle ${cycle - 1}) — you MUST resolve ALL of these before finishing:\nScore: ${critique.score}\nSummary: ${critique.summary}\nItems to fix:\n${critique.questions.map((q, i) => `  ${i + 1}. ${q}`).join('\n')}\n\nIMPORTANT: This is cycle ${cycle} of ${MAX_CYCLES} — the final cycle. Fix every item above completely. Do not leave any item partially addressed.`
    : ''

  genResult = await agent(
    `${PROJECT_CONTEXT}

PLAN FROM wfm-planner:
${plan}
${prevCritiqueNote}

Your task: implement every sub-task in the plan above.
Read the relevant files at the PATH shown above before making any changes.
Build everything completely — no stubs, no TODOs, no placeholders.
All WFM domain rules in the project context are non-negotiable.
When done, produce a numbered list mapping each plan sub-task to exactly what changed and in which file.`,
    {
      agentType: 'wfm-generator',
      label: `wfm-generator-c${cycle}`,
      phase: `Generate — cycle ${cycle}`
    }
  )

  log(`Generator cycle ${cycle} complete.`)

  /* ── Critique ── */
  phase(`Critique — cycle ${cycle}`)
  log(`Invoking wfm-critic (cycle ${cycle} of ${MAX_CYCLES})...`)

  critique = await agent(
    `${PROJECT_CONTEXT}

ORIGINAL REQUEST:
${request}

PLAN THAT WAS IMPLEMENTED:
${plan}

GENERATOR OUTPUT SUMMARY:
${genResult}

Your task: read the project files at the PATH shown above and critique ONLY the changes
introduced by the generator above — do not raise pre-existing issues that are unrelated
to this request.

SIMULATE, DO NOT JUST READ — mandatory before you score:
- For any inline event handler changed (onclick/oninput/onchange), reconstruct the EXACT
  attribute string the browser receives after template interpolation. A double quote from
  JSON.stringify inside a double-quoted onclick attribute BREAKS the handler — it will never
  fire. If the handler would not fire, that is a BLOCKING Amber, not a passing change.
- For any data-capture/display change, name the exact write path (with key casing, e.g.
  h.years.Y1.actual.voice) and the exact read path, then check every gate/filter BETWEEN
  them. If a value can be entered but will not appear where the user expects it, that is
  BLOCKING even when each line is individually correct.
- Verify the SPECIFIC bug each sub-task claims to fix is actually fixed: locate the line that
  caused it and confirm the new code changes the runtime outcome. "Looks plausible" is not
  verification.
- Raise ONLY issues you can tie to a specific line AND a specific runtime symptom. Theoretical
  what-ifs, dead CSS, comment style, and audit-trail gaps are NOT grounds for Amber. A review
  with zero blocking issues is the expected outcome for a correct change — score it Green.

SCORING RULES — apply strictly:
- GREEN: All WFM formulas are correct. No user-facing text is false. No channel routing is broken.
  Minor issues such as dead CSS rules, audit-trail gaps, comment-only inconsistencies, and
  documentation style preferences do NOT block Green.
- AMBER: Incorrect HC formula result, false user-facing claim, broken channel routing, or
  data-loss risk introduced by this change.
- RED: Runtime crash, Infinity/NaN in calculation output, or direct violation of WFM domain rules.

Return structured output: score (Red/Amber/Green), questions (only blocking issues — omit
non-blocking observations), summary (one sentence).`,
    {
      agentType: 'wfm-critic',
      label: `wfm-critic-c${cycle}`,
      phase: `Critique — cycle ${cycle}`,
      schema: CRITIC_SCHEMA
    }
  )

  /* Guard: agent may return null if session limit is hit */
  if (!critique) {
    log(`Cycle ${cycle} critic returned null (session limit or agent failure). Pipeline blocked.`)
    critique = { score: 'Amber', summary: 'Critic agent did not complete — session limit hit. Re-run /implement.', questions: ['Critic agent was interrupted. Re-run /implement to retry.'] }
    break
  }

  log(`Cycle ${cycle} — Score: ${critique.score} — ${critique.summary}`)

  if (critique.score === 'Green') {
    log('Green score achieved. Proceeding to Ship phase.')
    break
  }

  if (cycle < MAX_CYCLES) {
    log(`Score is ${critique.score}. Starting cycle ${cycle + 1} to address critique questions...`)
  } else {
    log(`Score is ${critique.score} after ${MAX_CYCLES} cycles. Pipeline blocked — no commit will be made.`)
  }
}

/* ════════════════════════════════════════════════════════════════
   PHASE 4 — SHIP (Green only)
   Uses wfm-generator (has Bash tool) to run git add / commit / push.
   Commit message: "feat: <request truncated>" with pipeline note.
   Stages only the known source files — avoids __pycache__, OS files.
════════════════════════════════════════════════════════════════ */
if (critique && critique.score === 'Green') {
  phase('Ship')
  log('Green score confirmed — committing and pushing to GitHub...')

  const shortRequest = String(request).slice(0, 68).replace(/"/g, "'")
  const shortSummary = String(critique.summary || '').replace(/"/g, "'")

  await agent(
    `In the directory C:\\Users\\ranjan.prasad\\Downloads\\holiday-planning run these git commands in sequence using the Bash tool:

1. git add index.htm style-guide.css data_engine.py sample_data.json Readme.txt CLAUDE.md
2. git status (to confirm staged files)
3. git commit -m "feat: ${shortRequest}

WFM pipeline Green — ${shortSummary}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
4. git push origin main

Report the output of each command. If any command fails, report the error and stop.`,
    {
      agentType: 'wfm-generator',
      label: 'git-ship',
      phase: 'Ship'
    }
  )

  return {
    outcome: 'shipped',
    score: 'Green',
    plan,
    summary: critique.summary,
    questions: critique.questions
  }
}

/* ── Blocked (Amber or Red after all cycles) ── */
return {
  outcome: 'blocked',
  score: critique ? critique.score : 'unknown',
  plan,
  summary: critique ? critique.summary : 'Pipeline did not complete.',
  questions: critique ? critique.questions : []
}
