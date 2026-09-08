# Design Tokens — IT Service Portal

Reference file for all frontend build tasks. Derived from three enterprise
service-desk references (ServiceNow, and a similar internal-portal pattern),
adapted to this project's schema. Every Claude Code prompt for a page/component
should point to this file rather than restating values inline.

## Color

### Base palette

| Token                  | Hex       | Use                                                    |
| ---------------------- | --------- | ------------------------------------------------------ |
| `--chrome`             | `#141B2E` | Sidebar / persistent nav background                    |
| `--chrome-text`        | `#C8CDD8` | Nav text (inactive)                                    |
| `--chrome-text-active` | `#FFFFFF` | Nav text (active item)                                 |
| `--surface`            | `#F7F8FA` | Page background                                        |
| `--card`               | `#FFFFFF` | Cards, table rows, form panels                         |
| `--text-primary`       | `#1A1F2B` | Body text, headings                                    |
| `--text-secondary`     | `#5B6472` | Meta text, helper copy, timestamps                     |
| `--border`             | `#E2E5EA` | Hairline dividers, table/card borders                  |
| `--accent`             | `#2F5AA8` | Primary buttons, links, focus rings — **never** status |
| `--danger`             | `#B3261E` | Form validation errors only                            |

### Status / priority (reserved exclusively for `statuses` schema fields)

| State               | Hex       | Notes                           |
| ------------------- | --------- | ------------------------------- |
| Open                | `#2F5AA8` | Filled pill, white text         |
| In Progress         | `#C77D22` | Filled pill, white text         |
| Resolved            | `#2F7D5C` | Filled pill, white text         |
| Closed              | `#5B6472` | Outline pill, neutral           |
| Draft / Unsubmitted | `#8A93A3` | Outline pill only, never filled |

Priority reuses the same visual language (filled pill) but a distinct hue pair
so it's never confused with status at a glance — Low: `#5B6472` (outline),
Medium: `#C77D22` (outline), High: `#B3261E` (filled).

## Typography

- **Family:** Public Sans (single family — weight/size carries hierarchy, not
  a second display face). Fallback stack: `"Public Sans", system-ui, sans-serif`.
- **Base body:** 14px / 1.5 line-height (not the 16px marketing default —
  this is a dense tool, not a landing page)
- **Dense UI text** (table cells, meta, badges): 13px
- **Scale:** 12 / 13 / 14 / 16 / 20 / 24 / 32 — weights 400 (body) / 600
  (labels, table headers, emphasis) / 700 (page titles only)
- Sentence case throughout. No tracked-out ALL-CAPS labels. No arrow-suffixed
  button text ("Submit →").

## Layout

- Persistent dark sidebar (`--chrome`) + light content area (`--surface`).
  Sidebar is the wayfinding device — content never uses dark chrome.
- All in-app content is centered within the content area at its max-width
  — one consistent rule, no per-page-type exceptions. See Content width
  below for the exact values.
- Cards: **flat**, hairline `--border`, no box-shadow, no border-radius above
  4px. Explicitly avoiding the soft-shadow rounded-card-kit default.
- Forms: two-column field grouping where fields are logically related (label
  above input, not inline-left-labels).
- Tables: rule-separated rows, not bordered cards per row.
- Dashboard: card grid + right-rail summary widgets (stacked panels), no
  photographic hero.

### Content width

Content never spans the full remaining viewport — width is bounded by what
the content type actually needs, not by the available space. All content
types are centered within the content area at these max-widths:

| Content type       | Max-width | Applies to                                 |
| ------------------ | --------- | ------------------------------------------ |
| Single-action form | 640px     | Submit Service Request                     |
| Detail view        | 720px     | View Request Details, Track Request Status |
| Table / dashboard  | 1040px    | Requests Dashboard                         |

Login/Register are separate — they use `AuthShell` (full-viewport centered
card, no sidebar), not this table.

**Note on tables specifically:** centering a wide table trades off some
scan-ability (the eye travels further from a fixed left edge to reach the
first column on very wide viewports) for overall layout consistency across
the app. This was a deliberate choice, not an oversight — don't left-align
just the table to "fix" it.

Remaining space splits evenly on both sides of the centered content at
desktop widths above the max-width — that's expected, not a bug.

### Breakpoints

| Token         | Value | Behavior below this width                                                                                                                                                                         |
| ------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--bp-mobile` | 768px | Sidebar collapses to a top bar with a menu toggle (not persistent-visible); content padding reduces from 32px to 16px; all max-widths above become `100%` (fluid, minus padding) instead of fixed |

Every page built against `AppShell` must be checked at both a desktop width
(~1280px) and a mobile width (~375px) before a task is considered done —
this applies to every task from Task 1 onward, not just forms.

## Principles

1. Color signals status/priority and nothing else — a page should never use
   `--accent` blue and a status blue in a way that could be confused.
2. Density over whitespace: this tool is used repeatedly by the same people:
   optimize for scanning, not first-impression polish.
3. One typeface, doing all the work through weight and scale.
4. No decorative motion. Loading/success states may use a brief, purposeful
   transition (e.g. success banner fade-in) — nothing on hover-only flourish.
