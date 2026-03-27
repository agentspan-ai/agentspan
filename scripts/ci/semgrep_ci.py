#!/usr/bin/env python3

import argparse
import json
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Semgrep for a pull request and generate reviewer-facing output."
    )
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name form.")
    parser.add_argument("--head-sha", required=True, help="Head commit SHA for the pull request.")
    parser.add_argument("--base-sha", required=True, help="Base commit SHA for the pull request.")
    parser.add_argument("--report", required=True, help="Path to write the Semgrep JSON report.")
    parser.add_argument("--comment", required=True, help="Path to write the PR comment markdown.")
    parser.add_argument(
        "--github-output",
        required=True,
        help="Path to the GitHub Actions output file.",
    )
    parser.add_argument(
        "--job-summary",
        required=True,
        help="Path to the GitHub Actions job summary file.",
    )
    parser.add_argument(
        "--finding-limit",
        type=int,
        default=10,
        help="Maximum number of findings to include in the PR comment.",
    )
    return parser.parse_args()


def run_semgrep(report_path: Path, base_sha: str) -> int:
    command = [
        "semgrep",
        "scan",
        "--config",
        "p/default",
        "--error",
        "--disable-version-check",
        "--baseline-commit",
        base_sha,
        "--json",
        "--output",
        str(report_path),
        ".",
    ]
    return subprocess.run(command, check=False).returncode


def load_results(report_path: Path) -> list[dict]:
    if not report_path.exists():
        report_path.write_text('{"results":[]}\n', encoding="utf-8")
        return []

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        report_path.write_text('{"results":[]}\n', encoding="utf-8")
        return []

    return payload.get("results", [])


def changed_files_count(base_sha: str) -> int:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}...HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    return len([line for line in result.stdout.splitlines() if line.strip()])


def status_line(exit_code: int, findings: int) -> str:
    if exit_code == 0:
        return "no blocking findings"
    if findings > 0:
        return "blocking findings detected"
    return f"Semgrep exited with status {exit_code}"


def finding_lines(
    results: list[dict], repo: str, head_sha: str, finding_limit: int
) -> list[str]:
    lines = []
    for result in results[:finding_limit]:
        path = result.get("path", "unknown")
        start = result.get("start", {})
        line = start.get("line", 1)
        check_id = result.get("check_id", "semgrep")
        message = result.get("extra", {}).get("message", "Semgrep finding")
        url = f"https://github.com/{repo}/blob/{head_sha}/{path}#L{line}"
        lines.append(f"- [`{path}:{line}`]({url}) - **{check_id}**: {message}")
    return lines


def build_comment(
    repo: str,
    head_sha: str,
    base_sha: str,
    results: list[dict],
    exit_code: int,
    changed_files: int,
    finding_limit: int,
) -> str:
    findings = len(results)
    lines = [
        "## Semgrep Results",
        "",
        f"- Findings in changed files: {findings}",
        f"- Changed files in pull request: {changed_files}",
        f"- Baseline commit: `{base_sha}`",
        f"- Status: {status_line(exit_code, findings)}",
        "",
    ]

    if findings > 0:
        lines.append("### Findings")
        lines.extend(finding_lines(results, repo, head_sha, finding_limit))
        if findings > finding_limit:
            lines.extend(
                [
                    "",
                    f"_Showing first {finding_limit} findings. Full report is attached as `semgrep-results`._",
                ]
            )
    elif exit_code != 0:
        lines.append("Semgrep did not return findings, but the scan exited unsuccessfully. See the workflow logs.")
    else:
        lines.append("No Semgrep findings were introduced in the files changed by this pull request.")

    return "\n".join(lines) + "\n"


def write_github_outputs(output_path: Path, exit_code: int, findings: int) -> None:
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"exit_code={exit_code}\n")
        handle.write(f"findings={findings}\n")


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    comment_path = Path(args.comment)

    exit_code = run_semgrep(report_path, args.base_sha)
    results = load_results(report_path)
    changed_files = changed_files_count(args.base_sha)
    findings = len(results)

    comment = build_comment(
        repo=args.repo,
        head_sha=args.head_sha,
        base_sha=args.base_sha,
        results=results,
        exit_code=exit_code,
        changed_files=changed_files,
        finding_limit=args.finding_limit,
    )

    comment_path.write_text(comment, encoding="utf-8")
    with Path(args.job_summary).open("a", encoding="utf-8") as handle:
        handle.write(comment)
    write_github_outputs(Path(args.github_output), exit_code, findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
