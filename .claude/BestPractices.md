# CLAUDE.md

> This file is the entry point for every Claude Code session on this project.
> It is a map, not an encyclopedia. Read it first. Then follow the pointers.
> Every decision you cannot find here has been documented somewhere in `docs/`.

---

## Core Philosophy

**What Claude cannot see does not exist.**

Knowledge in Slack messages, Google Docs, or anyone's head is invisible to you. Only what is encoded in this repository — as code, markdown, schemas, or plans — is real context you can reason over. When in doubt, check `docs/` before assuming.

```
CLAUDE's KNOWLEDGE
        ▲
        │  encode into codebase as markdown
        │
  ┌─────┴──────────────────────────────────┐
  │  Unseen to Claude:                      │
  │  • Google Docs  • Slack  • Tacit knowledge │
  └─────────────────────────────────────────┘
```

All architectural decisions, team norms, and product choices must live in this repo or they do not exist for Claude.

---

## Repository Knowledge Structure

This file is ~100 lines. It is a table of contents. Deeper knowledge lives here:

```
CLAUDE.md                    ← you are here (map, not manual)
ARCHITECTURE.md              ← domain map, package layering, dependency rules
docs/
├── design-docs/
│   ├── index.md
│   └── core-beliefs.md
├── exec-plans/
│   ├── active/              ← current execution plans (checked in)
│   ├── completed/           ← finished plans (versioned history)
│   └── tech-debt-tracker.md
├── product-specs/
│   ├── index.md
│   └── [feature].md
├── references/              ← external library docs as llms.txt
├── DESIGN.md
├── FRONTEND.md
├── PLANS.md
├── QUALITY_SCORE.md
├── RELIABILITY.md
└── SECURITY.md
feature_list.json            ← canonical list of all features + pass/fail status
init.sh                      ← starts dev server + baseline smoke test
claude-progress.txt          ← session-by-session progress log
```

Read `ARCHITECTURE.md` before modifying any domain boundaries.
Read `docs/exec-plans/active/` before starting any complex task.

---

## Session Architecture

```
initialise agent ──────────────────► feature_list.json
        │                            init.sh
        ▼                            claude-progress.txt
coding agent 1 ◄────────────────────
        │        ────────────────────►  Each session:
       ...       ◄────────────────────  1. Read feature_list + progress files
        │        ────────────────────►  2. Read git log
        ▼        ◄────────────────────  3. Run init.sh
coding agent N ─────────────────────►  4. E2E test to verify env
                                        5. Start doing the work...
```

---

## Session Type 1: Initialise Agent (First Session Only)

**Trigger:** `feature_list.json` does not exist.

Do not write feature code. Your job is to build the environment every future session depends on.

### 1. Create `feature_list.json`

Expand the full spec into an exhaustive list of features. A real app may need 100–200+. More is better.

```json
[
  {
    "id": "feat-001",
    "category": "functional",
    "priority": 1,
    "description": "Unambiguous description of the feature",
    "steps": [
      "Concrete step a human user would take to verify this works",
      "Another verification step",
      "Final confirmation"
    ],
    "passes": false
  }
]
```

Rules:
- JSON only — never Markdown (less risk of accidental reformatting)
- Every feature starts `"passes": false`
- `priority` 1 = highest
- Categories: `functional`, `ui`, `auth`, `performance`, `security`, `accessibility`

### 2. Create `init.sh`

```bash
#!/bin/bash
# init.sh — run at the start of every session
echo "Starting environment..."
# install/verify deps
# start dev server
# basic health check
echo "Ready."
```

### 3. Create `claude-progress.txt`

```
# Progress Log

[INIT] Environment created.
- feature_list.json: N features, all failing
- init.sh: created
- Initial commit: done
- Next: begin feat-001
```

### 4. Scaffold `docs/` structure

Create the directory skeleton from the structure above. Stub each file with a one-line description of its purpose. Future sessions will fill them in.

### 5. Initial git commit

```bash
git add .
git commit -m "chore: initialise Claude Code agent environment

- feature_list.json (N features)
- init.sh
- claude-progress.txt
- docs/ scaffold"
```

---

## Session Type 2: Coding Agent (All Subsequent Sessions)

Execute phases in order. Do not skip or reorder.

---

### Phase 1 — Orient

```bash
pwd
cat claude-progress.txt
git log --oneline -20
cat feature_list.json
```

Read before touching anything. Never assume you know the current state.

---

### Phase 2 — Verify Environment

```bash
bash init.sh
```

Then run a baseline end-to-end test using browser automation (Puppeteer MCP or Chrome DevTools MCP), not curl, not unit tests. Verify the app works as a real user would.

**E2E validation loop:**

```
Claude ──► Select target + clear console ──► App + Chrome DevTools
Claude ──► Snapshot BEFORE                ──► App
Claude ──► Trigger UI path                ──► App
                                               └──► Runtime events ──► Chrome DevTools
Claude ──► Snapshot AFTER                 ──► App
Claude ──► Apply fix + restart            ──► App
┌─────────────────────────────────────────────┐
│  LOOP until clean:                           │
│  Claude ──► Re-run validation ──► App        │
└─────────────────────────────────────────────┘
```

If the baseline is broken:
1. `git log` to find last known-good commit
2. `git revert` or `git checkout <hash> -- <file>` to restore it
3. Commit the fix separately with message `fix: restore baseline before feat-NNN`

> ⚠️ Never build a new feature on top of a broken baseline.

---

### Phase 3 — Do The Work

#### 3.1 Pick exactly one feature

Select the single highest-`priority` feature in `feature_list.json` where `"passes": false`.

**One feature per session. No exceptions.** Multiple features in one session creates half-implemented states that break future sessions.

For complex features, check `docs/exec-plans/active/` for an existing plan. If none exists, create one before coding:

```markdown
# Execution Plan: feat-NNN — [Feature Name]

## Goal
One sentence.

## Steps
- [ ] Step 1
- [ ] Step 2

## Decision Log
- [date] Chose X over Y because Z
```

Check this plan into `docs/exec-plans/active/` before starting.

#### 3.2 Implement

Write clean, production-quality, well-documented code. Every commit should be mergeable to `main`. No WIP state, no commented-out blocks, no undocumented stubs.

Apply the layered architecture (see `ARCHITECTURE.md`). Dependencies must only flow in permitted directions.

#### 3.3 Test end-to-end

Walk through every step in the feature's `"steps"` array using browser automation — exactly as a human user would. Query logs and metrics if available.

> ⚠️ Do not mark passing after reading code only.
> ⚠️ Do not mark passing after unit tests only.
> ⚠️ Do not mark passing after curl only.
> Browser verification is required. Every time.

#### 3.4 Update `feature_list.json`

After successful e2e verification only:

```json
{ "id": "feat-001", "passes": true }
```

> ⚠️ Never remove or rewrite a feature's `description` or `steps`.
> ⚠️ Only change `"passes"` from `false` to `true`. Never the reverse.

---

### Phase 4 — Close The Session

Leave the codebase in a state a teammate could immediately continue from.

#### 4.1 Git commit

```bash
git add .
git commit -m "feat(feat-001): [feature name]

What was built:
- ...

Tested via:
- E2E browser automation: [describe path tested]
- Logs/metrics verified: [yes/no, what was checked]

Known limitations:
- ...

Next session: [one-line recommendation]"
```

#### 4.2 Update `claude-progress.txt`

```
[SESSION N]
- Feature: feat-001 — [description]
- Status: Complete / Partial
- Tested: E2E via [Puppeteer/Chrome DevTools MCP]
- Bugs fixed: [pre-existing issues resolved]
- Known issues: [anything unresolved]
- Next: feat-002, focus on [area]
```

#### 4.3 Close execution plan (if used)

If a plan was created, move it from `docs/exec-plans/active/` to `docs/exec-plans/completed/`.

---

## Knowledge Management Rules

### If it's not in the repo, it doesn't exist

Any decision, norm, or pattern that lives only in a chat, doc, or person's head is invisible. Before ending a session, ask: did I make any decisions that future sessions need to know? If yes, encode them:

- Architectural decisions → `ARCHITECTURE.md` or a design doc
- Engineering norms → `docs/core-beliefs.md`  
- Feature context → `docs/product-specs/[feature].md`
- Technical debt noticed → `docs/exec-plans/tech-debt-tracker.md`

### Documentation freshness

Stale documentation is worse than no documentation. If you encounter docs that don't match the code:
1. Fix the docs in the same PR as the code change
2. Flag in `claude-progress.txt` if it's beyond your current scope

### Progressive disclosure

Start with `CLAUDE.md`. It points you to `ARCHITECTURE.md`. That points you to domain docs. Do not scan the entire `docs/` directory up front — follow the pointers.

---

## Architecture Rules

See `ARCHITECTURE.md` for the full diagram. The key invariant:

```
Business Logic Domain
─────────────────────────────────────────
Utils (external)
        │
        ▼
   Providers  ──────────────► App Wiring + UI
        │                          ▲
        ▼                          │
   Service ──► Runtime ────────────┘
        ▲
        │
  Types ──► Config ──► Repo
─────────────────────────────────────────
Dependencies only flow forward through layers.
Cross-cutting concerns (auth, telemetry, feature flags) enter only via Providers.
```

These rules are enforced by linters and CI — violations will fail the build. Do not work around them. If a lint rule is wrong, open a PR to change the rule, don't suppress the error.

---

## Failure Modes & Fixes

| Failure Mode | Fix |
|---|---|
| Building everything at once | One feature per session. Commit. Stop. |
| Declaring victory early | `feature_list.json`: any `false` = not done |
| Marking passing without e2e | Browser verification required, always |
| Broken baseline between sessions | `git revert` first, then fix, then commit separately |
| Guessing what last session did | Read `claude-progress.txt` + `git log` before anything |
| Patching broken code | Revert to known-good state, don't patch on broken |
| Decisions not in the repo | Encode in `docs/` before ending the session |
| Monolithic instruction files | Keep CLAUDE.md ~100 lines. Deeper content goes in `docs/` |
| Repeating bad patterns | Check `docs/core-beliefs.md` and linter output before implementing |

---

## Verification Is Not Optional

> Agents fail because they stop at "looks right."
> The harness must force **build → verify → fix** until evidence matches spec.

"Looks right" is not a passing state. Code compiling is not a passing state. A unit test passing is not a passing state.

A feature passes when a real user interaction, driven through the browser, produces the outcome described in `feature_list.json`. Nothing else counts.

The verification loop is non-negotiable:

```
build ──► verify (e2e) ──► evidence matches spec?
                                  │
                    NO ◄──────────┘
                     │
                  fix it
                     │
                     └──► build ──► verify ──► ...
                                  │
                    YES ◄─────────┘
                     │
              mark "passes": true
              commit
```

If you find yourself thinking "this should work" or "it looks correct" — stop. Run the browser test. Let evidence decide.

---

## Tool Philosophy: Generic Over Specialised

> Generic tools Claude natively understands **>** Specialised tooling.
>
> Specialised tools often encode premature decisions and become brittle.
> Prefer a small set of general-purpose tools: **filesystem, bash, tests, execution**.

Reach for specialised MCP tools only when a general-purpose approach is genuinely insufficient. A well-written bash script that uses standard CLI tools is almost always preferable to a bespoke tool with its own abstractions.

Why:
- Claude has deep, reliable knowledge of standard tools (bash, git, curl, grep, standard test runners)
- Specialised tools introduce abstractions Claude must learn from sparse context
- General tools compose freely; specialised tools often don't
- Specialised tooling encodes assumptions that may not age well

**Preferred tools:** `bash`, `git`, filesystem reads/writes, your standard test runner, Puppeteer/Chrome DevTools MCP for browser automation, LogQL/PromQL for observability queries.

**Before adding a new tool or dependency**, ask: can this be done with bash and a standard library? If yes, do that.

---

## Golden Principles

These apply to every line of code written. Violations should be caught by linters or flagged in review.

1. **Shared utilities over hand-rolled helpers.** Keep invariants centralized. If a utility exists, use it.
2. **Validate at boundaries.** Parse and validate all external data shapes on entry. Never probe data shapes speculatively.
3. **Structured logging only.** No ad-hoc `console.log`. Use the project's logging primitives.
4. **100% test coverage on shared utilities.** Core helpers must be fully tested.
5. **No dead code.** Remove anything unused. Do not comment out code and leave it.
6. **Small files.** If a file is growing large, decompose it. File size limits are enforced by linter.
7. **Boring is better.** Prefer stable, well-understood dependencies over clever ones. Agents model boring tech better.
8. **Generic tools over specialised tooling.** Reach for bash and standard tools first. Specialised tools are a last resort.
9. **Evidence over intuition.** Never mark work done based on how the code looks. Run the test. Trust the result.

---

## Session Start Checklist

```
[ ] pwd — correct directory?
[ ] cat claude-progress.txt
[ ] git log --oneline -20
[ ] cat feature_list.json — what's next?
[ ] bash init.sh — server started?
[ ] E2E smoke test — baseline clean?
[ ] Fix pre-existing bugs first (commit separately)
[ ] Pick ONE feature (highest priority, passes: false)
[ ] Check docs/exec-plans/active/ for existing plan
```

## Session End Checklist

```
[ ] Feature tested E2E in browser
[ ] feature_list.json updated (passes: true)
[ ] git commit with full message
[ ] claude-progress.txt updated
[ ] Any new decisions encoded in docs/
[ ] Execution plan moved to completed/ (if applicable)
[ ] Codebase mergeable — no WIP, no broken state
```

---

## Observability (If Configured)

If this project has a local observability stack, Claude can and should use it:

```
App ──► Vector (fan out) ──► Victoria Logs   ──► LogQL API
                         ──► Victoria Metrics ──► PromQL API
                         ──► Victoria Traces  ──► TraceQL API
                                                      │
                                               Claude queries,
                                               correlates, reasons
                                                      │
                                               Implement fix (PR)
                                               Restart app
                                               Re-run workload ──► loop
```

Prompts like "ensure this endpoint responds in under 500ms" or "no span in this user journey exceeds 2s" are tractable if observability is wired in. Check `docs/RELIABILITY.md` for current SLO targets.

---

## One Final Rule

If something fails repeatedly, the answer is almost never "try harder."

Ask instead: **what capability or context is missing?** Then encode that capability into the repository — as documentation, a new utility, a lint rule, or a test — so every future session benefits from it automatically.

Human taste and engineering judgment should be captured once and enforced everywhere.
c