# Delightful Newton - All Tests

Last updated: 2026-05-29

Attach this file first when the task involves testing, verification, or test debugging.

This is the fast operator guide for the testing surface:

- which runner to use
- what command to start with
- how to quickly debug common failures
- which deeper file to read next

---

## How This File Works

This is the `all-tests.md` entrypoint for the `tests/` context group. It follows the `all-*.md` routing convention:

1. Agents read `all-context.md` first and get routed here for testing tasks
2. This file gives quick decision rules and commands
3. For deeper details, agents follow the routing table below to specific docs

---

## What This Covers

- test runner selection
- quick commands
- fast debugging procedures
- current testing gaps worth remembering

## Read This When

Use this file when you need to:

- run tests after implementation
- decide between test runners
- debug failing tests

## Quick Routing

(No deeper test docs yet. Add routing entries here as they are created.)

## Quick Decision Guide

### Use `vitest` for everything

- All physics, math, and engine unit tests run through `vitest`.
- `npm run test` for CI (single run).
- `npm run test:watch` for active development.

## Default Verification Order

Unless the task clearly needs a different path:

1. run the unit tests for physics calculations
2. check typescript/javascript compilation errors if any
3. start the local Vite development server using `npm run dev`
4. verify simulator rendering, particle collisions, presets, and interactive gravity wells in the web browser.

## Commands

| Package / Directory | Runner | Command | Notes |
|---|---|---|---|
| root | vitest | `npm run test` | Executes physics unit tests once |
| root | vitest | `npm run test:watch` | Starts vitest in watch mode |
| root | vite | `npm run dev` | Spins up the local dev server at http://localhost:3000 |

## Debugging Quick Reference

- **JSDOM environment:** Our configuration uses `jsdom` inside Vitest to emulate the browser. Keep in mind that HTML5 Canvas context operations (like `getContext('2d')`) might require canvas mocks or behave differently than real browsers. Put any mock setup inside `vite.config.js`.
- **Softening factor:** Gravity calculations use a softening factor of `100` to prevent division by zero or extreme velocity accelerations when particles approach too closely. If forces appear incorrect, verify that this factor is applied consistently in both implementation and tests.
- **Delta time (dt) limits:** The physics update loop clamps `dt` to `3` to prevent physics explosions when the rendering thread lags or experiences frame hitches.

## Known Gaps

- No Playwright end-to-end tests are written yet. Browser interaction must be verified manually.
- No automated UI performance stress testing scripts are implemented (performance is measured via the UI dashboard's FPS counter).
