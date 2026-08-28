# Notion Dry-Run Auth Debug Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an explicit auth debug flag and make `--dry-run` print the exact page payload preview before validating Notion database access.

**Architecture:** Keep the script as a single-file CLI. Add small pure helper functions for masking and diagnostics, restructure the main flow so the preview object is computed before the Notion schema check, and make dry-run perform a read-only database validation after printing the preview.

**Tech Stack:** Python 3.12, Click, requests, loguru, unittest

---

### Task 1: Plan the new CLI behavior

**Files:**
- Modify: `notion_ingest_github_apple_ai.py`

**Step 1: Write the failing test**

Add a test that expects a preview object to be printable before a Notion validation failure, and a test that expects masked auth diagnostics.

**Step 2: Run test to verify it fails**

Run: `python -m unittest -v`
Expected: FAIL because helper functions and CLI flow do not exist yet.

**Step 3: Write minimal implementation**

Add helper functions for source detection, masking, suspicious value hints, and preview construction. Add `--debug-auth` and adjust `--dry-run` flow.

**Step 4: Run test to verify it passes**

Run: `python -m unittest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-03-10-notion-dry-run-auth-debug.md tests/test_notion_ingest_github_apple_ai.py notion_ingest_github_apple_ai.py
git commit -m "feat: add dry-run Notion validation diagnostics"
```
