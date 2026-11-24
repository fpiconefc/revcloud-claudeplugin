#!/usr/bin/env python3
"""Lint an rc-* skill against this repository's authoring conventions.

Checks shape, not truth. A skill that passes can still be wrong; the human review
in SKILL.md step 6 is what catches that. What this catches is the mechanical
sloppiness that is tedious to spot by eye: thin descriptions, orphaned reference
files, scripts that do not compile, and sentences that assert a Revenue Cloud fact
without saying where it came from.

Usage:
    python3 lint_skill.py path/to/skill-dir
    python3 lint_skill.py plugins/*/skills/*          # lint them all
    python3 lint_skill.py --strict path/to/skill-dir  # warnings become errors

Exit codes: 0 clean, 1 errors found, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import py_compile
import re
import sys
import tempfile
from pathlib import Path

MIN_DESCRIPTION_CHARS = 200
MAX_BODY_LINES = 500

# Phrases that mark a claim as sourced. A claim-shaped sentence near one of these
# is treated as marked.
PROVENANCE_MARKERS = re.compile(
    r"\b(per the (developer )?guide|developer guide|the guide (says|lists|states)"
    r"|in (this|the) org|org \w+|swept|describe|fingerprint|DOCS|ORG"
    r"|según la guía|en la org|en esta org)\b",
    re.IGNORECASE,
)

# Sentences that assert platform behaviour. Deliberately narrow: a noisy linter
# gets ignored, which is worse than no linter.
CLAIM_SHAPES = [
    (re.compile(r"\b[A-Z][A-Za-z]+(?:__c)?\.[A-Z][A-Za-z0-9_]+\s+(accepts|holds|contains|stores|is required|defaults to)\b"),
     "asserts a field's behaviour"),
    (re.compile(r"\b(is|are) (always|never) (available|required|supported|populated)\b"),
     "asserts an absolute about availability"),
    (re.compile(r"\bavailable (in|from) API version\b", re.IGNORECASE),
     "asserts an API version"),
    (re.compile(r"\b(requires|needs) (a |an )?(licence|license|permission set|add-on)\b", re.IGNORECASE),
     "asserts a licensing requirement"),
]

HEDGES = re.compile(r"\b(may|might|typically|usually|generally|in some cases|often)\b", re.IGNORECASE)
MAX_HEDGE_RATIO = 0.04  # hedges per line of body


class Report:
    def __init__(self, name: str) -> None:
        self.name = name
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def emit(self) -> None:
        status = "FAIL" if self.errors else ("warn" if self.warnings else "ok")
        print(f"[{status}] {self.name}")
        for e in self.errors:
            print(f"    error: {e}")
        for w in self.warnings:
            print(f"    warn:  {w}")


def split_frontmatter(text: str) -> tuple[str | None, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None, text
    return m.group(1), m.group(2)


def scalar(frontmatter: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*(.+?)(?=\n\S|\n*$)", frontmatter, re.S | re.M)
    if not m:
        return None
    return m.group(1).strip().strip("'\"")


def lint(skill_dir: Path) -> Report:
    rep = Report(str(skill_dir))
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        rep.error("no SKILL.md")
        return rep

    text = skill_md.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)

    if frontmatter is None:
        rep.error("no YAML frontmatter between --- fences")
        return rep

    # --- frontmatter -------------------------------------------------------
    name = scalar(frontmatter, "name")
    if not name:
        rep.error("frontmatter has no name")
    elif name != skill_dir.name:
        rep.error(f"name '{name}' does not match directory '{skill_dir.name}'")

    if not scalar(frontmatter, "version"):
        rep.warn("no version; this repo versions every skill")

    description = scalar(frontmatter, "description")
    if not description:
        rep.error("frontmatter has no description")
    else:
        if len(description) < MIN_DESCRIPTION_CHARS:
            rep.error(
                f"description is {len(description)} chars; under {MIN_DESCRIPTION_CHARS} "
                "it under-triggers. Add the phrasings a user would type."
            )
        if '"' not in description and "'" not in description:
            rep.warn("description quotes no trigger phrases; skills under-trigger without them")
        if not re.search(r"\b(not for|rather than|instead of|no para)\b", description, re.I):
            rep.warn("description does not say what the skill is NOT for")

    # --- body --------------------------------------------------------------
    body_lines = body.splitlines()
    if len(body_lines) > MAX_BODY_LINES:
        rep.warn(f"body is {len(body_lines)} lines; push detail into references/")
    if re.search(r"^##?\s*when to use", body, re.I | re.M):
        rep.warn("'when to use' belongs in the description; the body is read after triggering")

    hedges = len(HEDGES.findall(body))
    if body_lines and hedges / len(body_lines) > MAX_HEDGE_RATIO:
        rep.warn(f"{hedges} hedging words in {len(body_lines)} lines; mark claims instead of hedging")

    # --- unmarked claims ---------------------------------------------------
    in_code = False
    for n, line in enumerate(body_lines, start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip():
            continue
        for pattern, why in CLAIM_SHAPES:
            if pattern.search(line):
                window = "\n".join(body_lines[max(0, n - 4):n + 2])
                if not PROVENANCE_MARKERS.search(window):
                    rep.warn(f"line {n}: {why}, no nearby DOCS/ORG marker -- {line.strip()[:70]}")
                break

    # --- bundled resources -------------------------------------------------
    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for ref in sorted(refs_dir.glob("*.md")):
            if ref.name not in body:
                rep.warn(f"references/{ref.name} is never mentioned in SKILL.md; it will not be read")

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        for script in sorted(scripts_dir.glob("*.py")):
            try:
                with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
                    py_compile.compile(str(script), cfile=tmp.name, doraise=True)
            except py_compile.PyCompileError as exc:
                rep.error(f"scripts/{script.name} does not compile: {exc.msg.splitlines()[0]}")
            if script.name not in body:
                rep.warn(f"scripts/{script.name} is never invoked from SKILL.md")

    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint rc-* skills.")
    ap.add_argument("paths", nargs="+", help="skill directories")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    dirs = [Path(p).resolve() for p in args.paths if Path(p).is_dir()]
    if not dirs:
        print("no skill directories given", file=sys.stderr)
        return 2

    failed = 0
    for d in dirs:
        rep = lint(d)
        rep.emit()
        if rep.errors or (args.strict and rep.warnings):
            failed += 1

    print()
    print(f"{len(dirs)} skill(s) linted, {failed} failing"
          f"{' (strict)' if args.strict else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
