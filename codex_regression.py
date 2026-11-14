"""Run the Windows path matrix and issue #60916 check against one Codex build."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

import winpath


REPOSITORY = Path(__file__).resolve().parent
PROBE = REPOSITORY / "examples" / "check_codex_paths.py"
FIXTURE = REPOSITORY / "examples" / "sample.txt"


def server_version(executable, scratch):
    profile = scratch / "version-profile"
    profile.mkdir()
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(name, None)
    env["CODEX_HOME"] = str(profile)
    response = subprocess.run(
        [str(executable), "--version"], cwd=scratch,
        env=env,
        capture_output=True, encoding="utf-8", timeout=15, check=True,
    )
    version = response.stdout.strip()
    if not re.fullmatch(r"codex-(?:app-server|cli) [0-9][0-9A-Za-z.+-]*", version):
        raise ValueError("Could not identify the Codex executable version")
    return version


def ordinary_paths(executable, scratch):
    raw_report = scratch / "matrix.json"
    exit_code = winpath.main([
        "--mode", "file", "--fixture", str(FIXTURE), "--root", str(scratch),
        "--timeout", "40", "--json", str(raw_report), "--", sys.executable,
        str(PROBE), "--server", str(executable), "--file", "{input}",
    ])
    raw = json.loads(raw_report.read_text(encoding="utf-8"))
    cases = []
    for row in raw["cases"]:
        case = {
            key: row[key]
            for key in ("scenario", "variant", "status", "child_exit_code", "path_difference")
        }
        if row["child_exit_code"] in (0, 1):
            details = json.loads(row["stdout_tail"])
            if row["child_exit_code"] == 0 and details != {
                "status": "passed", "exact_name_count": 1, "content_matches": True
            }:
                raise ValueError("A passing path did not verify the original name and bytes")
            for key in ("exact_name_count", "content_matches", "rpc_error_code"):
                if key in details:
                    case[key] = details[key]
        else:
            exit_code = 2
            # The path itself was not tested if startup, transport, or setup failed.
            case["path_difference"] = False
            if row["child_exit_code"] == 2:
                case["status"] = "probe-error"
        cases.append(case)
    expected_count = 2 * len(winpath.VARIANTS)
    if exit_code == 0 and len(cases) != expected_count:
        raise ValueError(f"Expected {expected_count} file path cases")
    return {"exit_code": exit_code, "cases": cases}


def filename_collision(executable, scratch):
    response = subprocess.run(
        [sys.executable, str(PROBE), "--server", str(executable), "--collision"],
        cwd=scratch, capture_output=True, encoding="utf-8", timeout=120,
    )
    if response.returncode not in (0, 1, 2):
        raise ValueError(f"Unexpected exit code from the filename probe: {response.returncode}")
    details = json.loads(response.stdout)
    error = details.pop("error", None)
    if error:
        print(f"Filename probe: {ascii(error)}", file=sys.stderr)
    return {"exit_code": response.returncode, **details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, type=Path, help="Native Codex or App Server executable")
    parser.add_argument("--root", type=Path, default=Path(tempfile.gettempdir()),
                        help="Existing writable ASCII directory without whitespace")
    parser.add_argument("--report", type=Path, default=Path("codex-regression.json"),
                        help="Output JSON path (default: codex-regression.json)")
    args = parser.parse_args()

    report_path = args.report.resolve()
    executable = args.server.resolve()
    if report_path == executable:
        parser.error("--report and --server must refer to different files")
    if not report_path.parent.is_dir() or report_path.is_dir():
        parser.error("--report must name a file in an existing directory")
    report = {
        "schema_version": 1,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "exit_code": 2,
    }
    try:
        if os.name != "nt":
            raise ValueError("Run this check on native Windows")
        if not executable.is_file() or executable.suffix.lower() != ".exe":
            raise ValueError("--server must point to an existing native .exe")
        root = args.root.resolve(strict=True)
        if not root.is_dir() or not str(root).isascii() or any(c.isspace() for c in str(root)):
            raise ValueError("--root must be an existing directory with an ASCII path and no whitespace")
        with tempfile.TemporaryDirectory(prefix="codex-regression-", dir=root) as directory:
            scratch = Path(directory)
            report["server_version"] = server_version(executable, scratch)
            report["ordinary_paths"] = ordinary_paths(executable, scratch)
            report["filename_collision"] = filename_collision(executable, scratch)
        report["exit_code"] = max(
            report["ordinary_paths"]["exit_code"], report["filename_collision"]["exit_code"]
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Codex regression check: {ascii(str(error))}", file=sys.stderr)
    try:
        winpath.write_report(report_path, report)
    except OSError as error:
        print(f"Could not write report: {ascii(str(error))}", file=sys.stderr)
        return 2
    print(f"Codex regression report: {ascii(str(report_path))} (exit {report['exit_code']})")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
