# Delightful Newton - All Context

Last updated: 2026-05-29

This file is the root context entrypoint for the repo.

Use it for two things:

1. quick routing to the right context pack or root file
2. broad architecture and repository understanding

Start here before loading deeper context files.

---

## How This File Works (the `all-*.md` Convention)

Every `process/context/` directory has one `all-*.md` entrypoint that acts as an attachable quick router for that domain. This root file (`all-context.md`) is the top-level router. Context groups each have their own `all-{group}.md` entrypoint.

**The pattern:**

```
process/context/
  all-context.md                      <-- THIS FILE: root router
  planning/
    all-planning.md                   <-- group router for planning
    example-antigravity-plan.md       <-- deep doc within the group
  tests/
    all-tests.md                      <-- group router for tests
```

---

## Quick Start

For most substantial tasks:

1. read this file first
2. choose the smallest relevant root file or context group from the tables below
3. only then load deeper files

---

## Current Root Entry Points

| File | Read when |
|---|---|
| `process/context/all-context.md` | any substantial planning, research, review, or implementation task |
| `process/context/tests/all-tests.md` | testing, verification, debugging test failures, execution planning |
| `process/context/planning/all-planning.md` | plan-shape calibration, planning examples, SIMPLE vs COMPLEX reference docs |

## Current Context Groups

| Group | Entry point | Scope |
|---|---|---|
| `planning/` | `process/context/planning/all-planning.md` | plan-shape calibration, planning examples, SIMPLE vs COMPLEX reference docs |
| `tests/` | `process/context/tests/all-tests.md` | test runners, commands, debugging, gaps |

## Task Routing Table

| If the task involves... | Start with |
|---|---|
| architecture or stack questions | this file |
| testing or verification | `process/context/tests/all-tests.md` |
| creating a new plan | `process/context/planning/all-planning.md` |

## Context Group Lifecycle

Context groups are durable knowledge domains, not feature folders.

Create a group when:

- a topic has 3+ durable docs
- a single doc exceeds roughly 800 lines with separable subtopics
- multiple agents repeatedly need only one slice of a large context file
- the topic maps to a stable operational domain (tests, infra, database, auth, UI, workflows, etc.)

Do not create a group when:

- the content is a temporary report
- the content is a plan or execution artifact
- the topic is feature-specific and belongs in `process/features/...`

Move or split one group at a time. Use `all-{group}.md` entrypoints.

## Naming Convention

There are no `README.md` files inside `process/context/`.

Canonical entrypoints use `all-*.md`:

- root: `process/context/all-context.md`
- group: `process/context/{group}/all-{group}.md`

Each `all-{group}.md` file should act as the attachable quick router for that domain:

- tell the agent what the group covers
- give quick procedures and decision rules
- route to smaller deeper files

## Context Update Protocol

When durable project knowledge changes:

1. update the smallest relevant context file
2. update this file if routing, ownership, naming, or groups changed
3. update the owning `all-{group}.md` entrypoint when a group exists

---

## Repository Structure

```
delightful-newton/
  .agents/            -- Symlink junction pointing to .claude/skills
  .antigravity/       -- Antigravity specific configuration and agent models
  .claude/            -- Claude IDE specific configuration
  .codex/             -- Codex specific config files
  process/            -- RipER-5 methodology files
    _seeds/           -- Template configurations and guides
    context/          -- Durable repository context docs (this directory)
      planning/       -- Plan guidelines and example specs
      tests/          -- Test definitions and commands
    development-protocols/ -- Spec-Driven Development instructions
    features/         -- Feature scoping sandbox
    general-plans/    -- In-flight, backlog, completed plans and reports
  src/
    main.js           -- Simulator engine, Newtonian equations, and event handlers
    style.css         -- Premium glassmorphism design system & micro-animations
    physics.test.js   -- Unit tests verifying Newtonian forces
  index.html          -- Interactive UI layout with sliders and stats panels
  package.json        -- Package dependencies and running scripts
  vite.config.js      -- Vite configuration for server and testing environment
  ANTIGRAVITY.md      -- Compatibility guide for Antigravity main session
```

## Technology Stack

- **Framework:** Vanilla HTML5 / JavaScript (ES Modules)
- **Styling:** Custom Vanilla CSS with HSL variables, glassmorphism filters, and CSS keyframe animations
- **Bundler/Dev Server:** Vite ^5.2.0
- **Test Runner:** Vitest ^1.6.0
- **Test Environment:** JSDOM ^24.1.0
- **Runtime:** Node.js (via agy-node ^24.14.0)
- **Deployment/Preview:** Vite preview server on port 3000

## Key Patterns and Conventions

- **Visual Aesthetics:** Dark mode by default, glassmorphic UI overlay dashboard, dynamic backglow orbs shift colors on Antigravity mode.
- **Physics Engine:** Newton's Law of Universal Gravitation `F = G * m1 * m2 / r^2` with softening constant to prevent velocity spikes. Collision detection uses axis distance check and elastic collision resolution using impulse scalars.
- **Render Loop:** requestAnimationFrame loop with delta-time normalization ensuring consistent physics frame rate across CPU configurations.
- **Interactive Spawning:** Mouse clicks spawn bodies calculating the perpendicular orbital velocity `v = sqrt(G * M / r)` ensuring immediate stable circular orbit behavior.
- **Diagnostics Metrics:** Active monitoring of FPS, MS Cost (render loop cycle execution time), and body count. Calculates dynamic Capacity Index based on performance strain.

## Environment and Configuration

**Config files:**
- `package.json` (npm scripts, dependency list)
- `vite.config.js` (dev server configurations, test engine mappings)
- `.antigravity/config.json` (agent definitions)

**Env variables:**
- `ANTIGRAVITY_AGENT` (running status indicator)
- `ANTIGRAVITY_PROJECT_ID` (unique identifier)

## Scan Metadata

- Generated: 2026-05-29T21:50:00Z
- HEAD: 672281d (Initial commit)
- Mode: Solo Dev
- Package manager: npm (Node v24.14.0 via agy-node)
