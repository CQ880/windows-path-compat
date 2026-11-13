"""Run a trusted test command against Windows path variants."""

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


VARIANTS = {
    "ascii": "sample",
    "space": "sample project",
    "cjk": "测试目录",
    "accent": "café",
    "cjk-space": "测试 项目",
}
INPUT = "{input}"
LOG_TAIL_BYTES = 2048


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, usage="%(prog)s --mode {cwd,file} [options] -- executable [args ...]"
    )
    parser.add_argument("--mode", required=True, choices=["cwd", "file"])
    parser.add_argument("--fixture", type=Path, help="File to copy for each case")
    parser.add_argument("--root", type=Path, default=Path(tempfile.gettempdir()),
                        help="Existing writable ASCII path with no whitespace")
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds per case (default: 30)")
    parser.add_argument("--json", type=Path, dest="report_path", help="Write a UTF-8 JSON report")
    parser.add_argument("--keep", action="store_true", help="Keep case directories for replay")
    option_args, separator, command = split_command(argv)
    args = parser.parse_args(option_args)
    args.command = command
    if not separator or not command or not command[0]:
        parser.error("provide a command after --")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number")
    if args.mode == "file" and (args.fixture is None or INPUT not in command[1:]):
        parser.error("file mode requires --fixture and a separate {input} argument")
    if INPUT in command[1:] and args.fixture is None:
        parser.error("{input} requires --fixture")
    return args


def split_command(argv):
    if "--" not in argv:
        return argv, False, []
    separator = argv.index("--")
    return argv[:separator], True, argv[separator + 1:]


def prepare(args):
    root = args.root.resolve(strict=True)
    if not root.is_dir() or not str(root).isascii() or any(c.isspace() for c in str(root)):
        raise ValueError("--root must be an existing directory with an ASCII path and no whitespace")
    args.root = root
    if args.fixture is not None:
        args.fixture = args.fixture.resolve(strict=True)
        if not args.fixture.is_file():
            raise ValueError("--fixture must be a file")
    executable = shutil.which(args.command[0])
    if not executable:
        raise ValueError(f"executable not found: {args.command[0]}")
    executable = Path(executable).resolve(strict=True)
    if executable.suffix.lower() not in {".exe", ".com"}:
        raise ValueError("use a Windows executable or explicitly invoke a script interpreter")
    args.command = [str(executable), *args.command[1:]]


def log_tail(stream):
    size = stream.tell()
    stream.seek(max(0, size - LOG_TAIL_BYTES))
    return stream.read().decode("utf-8", errors="replace"), size > LOG_TAIL_BYTES


def run_case(workspace, scenario, variant, path_name, fixture, command, timeout):
    case_dir = workspace / scenario / variant
    cwd = case_dir / (path_name if scenario == "cwd" else "run")
    cwd.mkdir(parents=True)
    input_path = None
    if fixture is not None:
        parent = case_dir / path_name if scenario == "file-parent" else cwd
        parent.mkdir(exist_ok=True)
        stem = path_name if scenario == "file-name" else "sample"
        input_path = parent / (stem + fixture.suffix)
        shutil.copyfile(fixture, input_path)
    argv = [str(input_path) if arg == INPUT else arg for arg in command]
    result = {
        "scenario": scenario, "variant": variant, "cwd": str(cwd),
        "input": str(input_path) if input_path else None, "argv": argv,
        "child_exit_code": None,
    }
    start = time.monotonic()
    with tempfile.TemporaryFile(dir=case_dir) as stdout, tempfile.TemporaryFile(dir=case_dir) as stderr:
        try:
            completed = subprocess.run(
                argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                timeout=timeout,
            )
            result["child_exit_code"] = completed.returncode
            result["status"] = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
        except OSError as error:
            result.update(status="launch-error", error=str(error))
        result["seconds"] = round(time.monotonic() - start, 3)
        result["stdout_tail"], result["stdout_truncated"] = log_tail(stdout)
        result["stderr_tail"], result["stderr_truncated"] = log_tail(stderr)
    return result


def run_suite(args, report):
    suffix = args.fixture.suffix if args.fixture else ""
    if suffix and not re.fullmatch(r"\.[A-Za-z0-9_-]+", suffix):
        raise ValueError("fixture extension must use ASCII letters, numbers, '-' or '_'")
    workspace = Path(tempfile.mkdtemp(prefix="winpath-", dir=args.root))
    report["workspace"] = str(workspace)
    scenarios = ("cwd",) if args.mode == "cwd" else ("file-parent", "file-name")
    try:
        fixture = None
        if args.fixture is not None:
            fixture = workspace / ("fixture" + suffix)
            shutil.copyfile(args.fixture, fixture)
        for scenario in scenarios:
            control_passed = False
            for variant, path_name in VARIANTS.items():
                try:
                    row = run_case(workspace, scenario, variant, path_name, fixture,
                                   args.command, args.timeout)
                except OSError as error:
                    row = {"scenario": scenario, "variant": variant, "status": "setup-error",
                           "child_exit_code": None, "error": str(error)}
                if variant == "ascii":
                    control_passed = row["status"] == "passed"
                row["path_difference"] = (
                    variant != "ascii" and control_passed and row["status"] == "failed"
                )
                report["cases"].append(row)
    finally:
        if not args.keep:
            try:
                if workspace.resolve() != workspace or workspace.parent != args.root:
                    raise ValueError("case directory moved outside its original location")
                shutil.rmtree(workspace)
                report["workspace_removed"] = True
            except (OSError, ValueError, RuntimeError) as error:
                report["errors"].append(f"cleanup failed for {workspace}: {error}")


def exit_code(report):
    if report["errors"] or any(
        row["status"] != "passed" and not row["path_difference"] for row in report["cases"]
    ):
        return 2
    return int(any(row["path_difference"] for row in report["cases"]))


def write_report(path, report):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False, prefix=".winpath-"
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(report, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = {
        "schema_version": 1, "mode": args.mode, "command": args.command,
        "fixture": str(args.fixture) if args.fixture else None, "timeout_seconds": args.timeout,
        "workspace": None, "workspace_removed": False, "errors": [], "cases": [],
    }
    report_path = None
    try:
        # Validate the output target separately so launch failures still get a report.
        if args.report_path is not None:
            candidate = args.report_path.resolve()
            if args.fixture is not None and candidate == args.fixture.resolve():
                raise ValueError("--json and --fixture must use different paths")
            if not candidate.parent.is_dir() or candidate.is_dir():
                raise ValueError("--json must name a file in an existing directory")
            report_path = candidate
        if sys.platform != "win32":
            raise ValueError("run this tool on native Windows")
        prepare(args)
        report["fixture"] = str(args.fixture) if args.fixture else None
        report["command"] = args.command
        run_suite(args, report)
    except (ValueError, OSError, RuntimeError) as error:
        report["errors"].append(str(error))
    report["exit_code"] = exit_code(report)
    if report_path is not None:
        try:
            write_report(report_path, report)
        except OSError as error:
            report["errors"].append(f"cannot write JSON report: {error}")
            report["exit_code"] = 2
    for row in report["cases"]:
        label = "path-difference" if row["path_difference"] else row["status"]
        print(f'{row["scenario"]:<12} {row["variant"]:<9} {label}'
              f' (child exit {row["child_exit_code"]})')
        detail = row.get("error") or row.get("stderr_tail")
        if row["status"] != "passed" and detail:
            print(f"  {ascii(detail.strip())}", file=sys.stderr)
    for error in report["errors"]:
        print(f"winpath: {ascii(error)}", file=sys.stderr)
    if args.keep and report["workspace"]:
        print(f'Workspace: {report["workspace"]}')
    if report_path is not None and not any(
        error.startswith("cannot write JSON report:") for error in report["errors"]
    ):
        print(f"Report: {ascii(str(report_path))}")
    if report["exit_code"] != 0 and report["cases"] and not args.keep:
        print("Repeat the command with --keep before -- to retain case files.")
    summary = {0: "passed", 1: "path difference found", 2: "incomplete or invalid"}
    print(f'Overall: {summary[report["exit_code"]]} (exit {report["exit_code"]})')
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
