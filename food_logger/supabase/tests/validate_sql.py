#!/usr/bin/env python3
"""Structural checks on the migration SQL, runnable without a database.

There is no Postgres to point at while developing, so this catches the class of
mistake that would otherwise only surface on a live project: an unbalanced
transaction, a table shipped without RLS, or a view missing security_invoker.

    python3 supabase/tests/validate_sql.py supabase/apply_all.sql

It is a lexical check, not a parser -- it will not catch a typo'd column name.
Run supabase/tests/timing_views.sql against a real database for that.
"""

import re
import sys
from pathlib import Path


def scan(sql):
    """Strip comments, strings and dollar-quoted bodies; track paren depth.

    Written as a scanner rather than a regex because SQL comments, '' escapes
    and $$ bodies nest in ways a regex silently gets wrong -- an earlier regex
    version of this reported zero policies in a file containing twenty-one.
    """
    out, i, n = [], 0, len(sql)
    depth = min_depth = 0
    while i < n:
        two = sql[i : i + 2]
        if two == "--":
            j = sql.find("\n", i)
            i = n if j == -1 else j
            continue
        if two == "/*":
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if sql[i] == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    if sql[i : i + 2] == "''":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append("''")
            continue
        m = re.match(r"\$[A-Za-z_]*\$", sql[i:])
        if m:
            tag = m.group(0)
            j = sql.find(tag, i + len(tag))
            if j == -1:
                raise ValueError(f"unterminated dollar-quote {tag}")
            i = j + len(tag)
            out.append(" DOLLARBODY ")
            continue
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            min_depth = min(min_depth, depth)
        out.append(sql[i])
        i += 1
    return "".join(out), depth, min_depth


def check(paths, expect_transaction, label):
    """Check a set of files as one logical unit.

    Migrations are applied in sequence, so cross-file facts -- a table created
    in one file and given RLS in the next -- are only meaningful once they are
    considered together. Checking each file alone reports every table in the
    schema migration as missing RLS, which is noise, not a finding.
    """
    src = "\n".join(Path(p).read_text(encoding="utf-8") for p in paths)
    code, depth, min_depth = scan(src)
    problems = []

    if depth:
        problems.append(f"parentheses left open: {depth}")
    if min_depth < 0:
        problems.append("closed more parentheses than were opened")

    if expect_transaction:
        for kw in ("begin;", "commit;"):
            got = len(re.findall(rf"(?m)^\s*{re.escape(kw)}", code))
            if got != 1:
                problems.append(f"expected exactly one top-level '{kw}', found {got}")

        commit_at = code.find("commit;")
        notify_at = code.find("notify pgrst")
        if notify_at == -1:
            problems.append("no 'notify pgrst' -- PostgREST would serve a stale schema cache")
        elif notify_at < commit_at:
            problems.append("notify pgrst is inside the transaction; NOTIFY only fires on commit")

    tables = re.findall(r"create table ([\w.]+)", code)
    enabled = set(re.findall(r"alter table ([\w.]+)\s+enable row level security", code))
    policies = re.findall(r"create policy (\w+) on ([\w.]+)", code)

    for t in tables:
        if t not in enabled:
            problems.append(f"table {t} has no RLS -- every row would be readable by anyone")

    for pname, t in policies:
        if not t.startswith("storage.") and t not in enabled:
            problems.append(f"policy {pname} targets {t}, which has no RLS enabled")

    names = [p[0] for p in policies]
    dupes = sorted({x for x in names if names.count(x) > 1})
    if dupes:
        problems.append(f"duplicate policy names (CREATE POLICY would fail): {dupes}")

    for name, opts in re.findall(r"create view ([\w.]+)\s*with \(([^)]*)\)", code):
        if "security_invoker" not in opts or "true" not in opts:
            problems.append(
                f"view {name} lacks security_invoker=true -- it would run as its owner "
                "and bypass RLS on the tables underneath"
            )
    for name in re.findall(r"create view ([\w.]+)\s*\n\s*as", code):
        problems.append(f"view {name} declares no options; it needs with (security_invoker = true)")

    print(label)
    print(f"  tables {len(tables)}  views {len(re.findall(r'create view', code))}  "
          f"rls {len(enabled)}  policies {len(policies)}")
    for p in problems:
        print(f"  PROBLEM: {p}")
    return not problems


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        results = [check(args, expect_transaction=len(args) == 1
                         and args[0].endswith("apply_all.sql"),
                         label=" + ".join(args))]
    else:
        here = Path(__file__).resolve().parent.parent
        migrations = sorted((here / "migrations").glob("*.sql"))
        results = [
            check([str(here / "apply_all.sql")], True, "apply_all.sql"),
            check([str(m) for m in migrations], False,
                  f"migrations/ ({len(migrations)} files, applied in sequence)"),
        ]
    print("\nOK" if all(results) else "\nFAILED")
    sys.exit(0 if all(results) else 1)
