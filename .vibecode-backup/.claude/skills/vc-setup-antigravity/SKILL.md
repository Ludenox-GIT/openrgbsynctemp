---
name: vc:setup-antigravity
description: Interactive agent harness setup specifically for Antigravity. Detects your stack, prompts you with interactive questions via ask_question, scaffolds the process folders, deep-scans your codebase, and writes context/all-context.md.
metadata:
  author: Antigravity-Team
  version: "1.0.0"
---

# VibeCo Antigravity Setup Skill

This skill scaffolds and initializes the `process/` directory and context files specifically optimized for Antigravity. It is a structured workflow that detects codebase technology stack, queries the user via the native `ask_question` tool, creates the necessary directories, studies the code, and populates routing contexts.

---

## Workflow Phases

### Phase 1: DETECT
1. Read `package.json` to identify framework, scripts, test runner, and packages.
2. Check for existing context or process layouts.
3. Classify project setup (New vs Existing) and report findings.

### Phase 2: ASK (Native Conversation)
Instead of freeform text prompts, use the native `ask_question` tool to gather structured metadata from the user. Formulate multiple-choice options for:
- Project Goal (e.g. "Web Application", "CLI Tool", "Backend Service", "Library")
- Test Hardening Priorities ("Unit Tests", "Integration/E2E Tests", "Visual Testing", "Performance Testing")
- Team Collaboration Size ("Solo Dev", "Small Team", "Large Engineering Group")
Follow up with additional open questions to understand details like architecture constraints and key conventions.

### Phase 3: SCAFFOLD
Create the standard RIPER-5 structure under `process/`:
- `process/context/` -> Durable context files (`all-context.md`, `tests/all-tests.md`)
- `process/context/planning/` -> Templates and blueprints
- `process/general-plans/active/` -> In-flight features
- `process/general-plans/completed/` -> Archived specs
- `process/general-plans/reports/` -> Diagnostic logs
- `process/general-plans/references/` -> Reference material
- `process/features/` -> Feature-specific workspaces

If layout migration is needed, rename directories according to standard compatibility maps (e.g. `plans/` -> `general-plans/active/`).

### Phase 4: STUDY
1. Analyze source directories to construct the repository tree.
2. Formulate accurate tech stack definitions with versions.
3. Write `process/context/all-context.md` containing real, detailed structure and conventions (no placeholders).
4. Write `process/context/tests/all-tests.md` with the exact test runner scripts and commands.

### Phase 5: VALIDATE
Verify setup completeness:
- Verify that `ANTIGRAVITY.md` is present in the root.
- Ensure that the 12 agent definitions are properly populated in `.antigravity/agents/`.
- Ensure no lingering `{{placeholder}}` patterns remain in context routers.
