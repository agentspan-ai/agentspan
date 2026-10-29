"""Release index: which release fixed what, and which clusters still run without the fix.

Two halves, one SQLite file (``<store>/release_index.db``, private — it names customers):

* **releases** — every Conductor release tag (``vX.Y.Z``, ``vX.Y.Z-rcN``) in the orkes-conductor
  repo, with the commits it added over the previous release, their PR numbers, ticket ids and
  the Java classes they touched. A fix backported to a release branch appears in that line's
  own release (matched across lines by PR number or subject).
* **fleet** — the Conductor version each cluster runs, read from its latest health check
  (``conductor.response.version``), no cluster access.

Code itself (files, calls, per-file history, Jira) is context-graph's job; this index adds the
release dimension it does not have, shaped so it can later be loaded into it as a connector.
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

STORE = Path(os.environ.get("ONCALL_STORE", os.path.expanduser("~/.oncall-agent")))
DB = STORE / "release_index.db"
# Tags that look like releases but are not (v6.0.0 was put on a main commit on 2026-09-21).
_IGNORED = set(filter(None, os.environ.get("ONCALL_IGNORE_RELEASE_TAGS", "v6.0.0").split(",")))
_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$")
_PR = re.compile(r"\(#(\d+)\)|Merge pull request #(\d+)")
_FIX = re.compile(r"\b(fix|fixes|fixed|bug|race|leak|npe|nullpointer|crash|regression|deadlock|stuck|"
                  r"prevent|correct|wrong|broken|timeout|oom|hang)", re.I)
_NOISE = re.compile(r"^(wip|revert|merge branch|bump|release|version|update version|\[maven-release)", re.I)
_TICKET = re.compile(r"\b((?:CCOR|ORK|CLOUD|CONDUCTOR|SAAS|SUP|OSS)-\d+)\b")

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (tag TEXT PRIMARY KEY, major INT, minor INT, patch INT, rc INT,
                                     created TEXT);
CREATE TABLE IF NOT EXISTS commits (sha TEXT PRIMARY KEY, date TEXT, subject TEXT, pr INT, author TEXT);
CREATE TABLE IF NOT EXISTS release_commits (tag TEXT, sha TEXT, PRIMARY KEY (tag, sha));
CREATE TABLE IF NOT EXISTS commit_classes (sha TEXT, class TEXT, path TEXT);
CREATE TABLE IF NOT EXISTS commit_tickets (sha TEXT, ticket TEXT);
CREATE TABLE IF NOT EXISTS fleet (cluster TEXT PRIMARY KEY, version TEXT, seen_at TEXT, org TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS cc_class ON commit_classes (class);
CREATE INDEX IF NOT EXISTS c_pr ON commits (pr);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def parse_version(v: str | None) -> tuple | None:
    """'5.5.11' / 'v5.6.0-rc4' / '5.2.96-SNAPSHOT' -> (5, 5, 11, rc) with rc=99 for a final release."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?", (v or "").strip())
    if not m:
        return None
    return int(m[1]), int(m[2]), int(m[3]), int(m[4]) if m[4] else 99


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=300).stdout


def index_releases(repo: str, db: sqlite3.Connection) -> int:
    """(Re)build the releases half from the repo's tags; returns the number of releases indexed."""
    # Release lines = main and the release branches; a tag reachable from none of them was cut
    # on a feature branch (seen: v6.0.0 on a CCOR-* branch) and is not a release.
    lines = [b.strip() for b in _git(repo, "for-each-ref", "--format=%(refname:short)",
                                     "refs/remotes/origin/main", "refs/remotes/origin/main-*").splitlines() if b.strip()]
    on_line: set[str] = set()
    for b in lines:
        on_line |= set(_git(repo, "tag", "--merged", b).split())
    tags = []
    for line in _git(repo, "for-each-ref", "--format=%(refname:short) %(creatordate:iso-strict)", "refs/tags").splitlines():
        name, _, created = line.partition(" ")
        m = _TAG.match(name)
        if m and name in on_line and name not in _IGNORED:
            tags.append((tuple(int(x) for x in m.groups(default="99")), name, created))
    tags.sort()
    done = {r["tag"] for r in db.execute("SELECT tag FROM releases")}
    added = 0
    for i, (ver, tag, created) in enumerate(tags):
        if tag in done:
            continue
        # The previous release on the same major.minor line, else the closest lower release.
        prev = next((t for v, t, _ in reversed(tags[:i]) if v[:2] == ver[:2]), tags[i - 1][1] if i else None)
        rng = f"{prev}..{tag}" if prev else tag
        log = _git(repo, "log", rng, "--format=@@%H\x1f%aI\x1f%an\x1f%s", "--name-only")
        db.execute("INSERT OR REPLACE INTO releases VALUES (?,?,?,?,?,?)", (tag, *ver, created))
        sha = None
        for row in log.splitlines():
            if row.startswith("@@"):
                sha, date, author, subject = row[2:].split("\x1f", 3)
                m = _PR.search(subject)
                pr = int(m[1] or m[2]) if m else None
                db.execute("INSERT OR IGNORE INTO commits VALUES (?,?,?,?,?)", (sha, date, subject, pr, author))
                db.execute("INSERT OR IGNORE INTO release_commits VALUES (?,?)", (tag, sha))
                for t in set(_TICKET.findall(subject)):
                    db.execute("INSERT INTO commit_tickets VALUES (?,?)", (sha, t))
            elif sha and row.endswith((".java", ".kt", ".groovy")) and "/test/" not in row:
                db.execute("INSERT INTO commit_classes VALUES (?,?,?)", (sha, Path(row).stem, row))
        added += 1
        if added % 25 == 0:
            db.commit()
    # Merged but not released yet: each line's head beyond its newest tag.
    db.execute("DELETE FROM release_commits WHERE tag LIKE 'unreleased:%'")
    for b in lines:
        newest = _git(repo, "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*", b).strip()
        if not newest:
            continue
        for row in _git(repo, "log", f"{newest}..{b}", "--format=%H\x1f%aI\x1f%an\x1f%s").splitlines():
            sha, date, author, subject = row.split("\x1f", 3)
            m = _PR.search(subject)
            db.execute("INSERT OR IGNORE INTO commits VALUES (?,?,?,?,?)",
                       (sha, date, subject, int(m[1] or m[2]) if m else None, author))
            db.execute("INSERT OR IGNORE INTO release_commits VALUES (?,?)", (f"unreleased:{b.split('/')[-1]}", sha))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('releases_indexed_at', ?)", (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
    db.commit()
    return added


def record_fleet(db: sqlite3.Connection, rows: list[dict]) -> int:
    """rows = [{cluster, version, seen_at, org}] from health checks."""
    for r in rows:
        db.execute("INSERT OR REPLACE INTO fleet VALUES (?,?,?,?)",
                   (r["cluster"], r["version"], r.get("seen_at"), r.get("org")))
    db.commit()
    return len(rows)


def _releases_after(db, version: tuple) -> list[sqlite3.Row]:
    return [r for r in db.execute("SELECT * FROM releases ORDER BY major, minor, patch, rc")
            if (r["major"], r["minor"], r["patch"], r["rc"]) > version]


def fixes_since(db: sqlite3.Connection, version: str, symbol: str | None = None, text: str | None = None,
                limit: int = 10) -> dict:
    """Commits in releases newer than ``version`` that touch ``symbol`` (a class) or mention ``text``,
    each with the FIRST release that carries it — on the cluster's own line first, then newer lines."""
    v = parse_version(version)
    if not v:
        return {"error": "unknown_version", "version": version}
    newer = _releases_after(db, v)
    if not newer:
        return {"version": version, "latest": None, "fixes": [], "verdict": "This cluster runs the newest indexed release."}
    tags = [r["tag"] for r in newer]
    q = """SELECT c.sha, c.subject, c.pr, c.date, rc.tag, r.major, r.minor, r.patch, r.rc
           FROM release_commits rc JOIN commits c ON c.sha = rc.sha JOIN releases r ON r.tag = rc.tag
           WHERE rc.tag IN (%s)""" % ",".join("?" * len(tags))
    args: list = list(tags)
    if symbol:
        q += " AND c.sha IN (SELECT sha FROM commit_classes WHERE class = ? OR path LIKE ?)"
        args += [symbol, f"%/{symbol}.%"]
    if text:
        q += " AND c.subject LIKE ?"
        args.append(f"%{text}%")
    q += " ORDER BY r.major, r.minor, r.patch, r.rc"
    seen, fixes = set(), []
    for r in db.execute(q, args):
        key = r["pr"] or r["subject"]
        if key in seen or _NOISE.match(r["subject"] or ""):
            continue  # the same fix on another line (backport): keep the earliest release
        seen.add(key)
        same_line = (r["major"], r["minor"]) == v[:2]
        fixes.append({"release": r["tag"], "final": r["rc"] == 99, "same_line": same_line, "pr": r["pr"],
                      "is_fix": bool(_FIX.search(r["subject"] or "")), "subject": r["subject"][:140],
                      "date": r["date"][:10]})
    # Real fixes first, on the cluster's own line first, in a final release first.
    fixes.sort(key=lambda f: (not f["is_fix"], not f["same_line"], not f["final"]))
    unreleased = [dict(r) for r in db.execute(
        """SELECT c.pr, substr(c.subject,1,140) subject, rc.tag FROM release_commits rc JOIN commits c ON c.sha=rc.sha
           WHERE rc.tag LIKE 'unreleased:%%' %s""" % (
            "AND c.sha IN (SELECT sha FROM commit_classes WHERE class = ?)" if symbol else
            ("AND c.subject LIKE ?" if text else "AND 0")), [symbol] if symbol else ([f"%{text}%"] if text else []))]
    latest_line = next((r["tag"] for r in reversed(newer) if (r["major"], r["minor"]) == v[:2] and r["rc"] == 99), None)
    latest = next((r["tag"] for r in reversed(newer) if r["rc"] == 99), newer[-1]["tag"])
    real = [f for f in fixes if f["is_fix"]]
    behind = sum(1 for r in newer if (r["major"], r["minor"]) == v[:2] and r["rc"] == 99)
    what = f" touching `{symbol}`" if symbol else (f" mentioning '{text}'" if text else "")
    verdict = (f"Runs {version}: {behind} newer release(s) on its own {v[0]}.{v[1]} line (latest {latest_line or 'none'}), "
               f"newest overall {latest}. {len(real)} fix(es){what} shipped since ({len(fixes)} changes in all)"
               + (f" — first: {real[0]['release']} {('#' + str(real[0]['pr'])) if real[0]['pr'] else ''} "
                  f"'{real[0]['subject'][:80]}'." if real else "."))
    return {"version": version, "latest_on_line": latest_line, "latest": latest, "releases_behind_on_line": behind,
            "fixes": fixes[:limit], "merged_not_released": unreleased[:limit], "verdict": verdict}


def exposed_clusters(db: sqlite3.Connection, pr: int | None = None, subject: str | None = None) -> dict:
    """Clusters running a version older than the first release (on their own line) that carries a fix."""
    q = "SELECT r.tag, r.major, r.minor, r.patch, r.rc FROM commits c JOIN release_commits rc ON rc.sha = c.sha " \
        "JOIN releases r ON r.tag = rc.tag WHERE " + ("c.pr = ?" if pr else "c.subject LIKE ?")
    first_by_line: dict[tuple, tuple] = {}
    for r in db.execute(q, [pr] if pr else [f"%{subject}%"]):
        v = (r["major"], r["minor"], r["patch"], r["rc"])
        if r["rc"] != 99:
            continue  # customers run final releases
        line = v[:2]
        if line not in first_by_line or v < first_by_line[line][0]:
            first_by_line[line] = (v, r["tag"])
    if not first_by_line:
        return {"error": "fix_not_in_any_release", "pr": pr, "subject": subject}
    exposed = []
    for f in db.execute("SELECT * FROM fleet"):
        v = parse_version(f["version"])
        if not v:
            continue
        fixed = first_by_line.get(v[:2])
        newest_fixed_line = max(first_by_line)
        if (fixed and v < fixed[0]) or (not fixed and v[:2] < newest_fixed_line):
            exposed.append({"cluster": f["cluster"], "version": f["version"],
                            "fix_in": fixed[1] if fixed else f"upgrade to {first_by_line[newest_fixed_line][1]}"})
    exposed.sort(key=lambda e: e["cluster"])
    return {"fixed_in": {f"{k[0]}.{k[1]}": t for k, (v, t) in sorted(first_by_line.items())},
            "exposed_count": len(exposed), "exposed": exposed}
