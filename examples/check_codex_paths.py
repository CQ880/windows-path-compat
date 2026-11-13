"""Check local Windows paths with Codex App Server's filesystem API."""

import argparse
import base64
import itertools
import json
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import subprocess
import tempfile
from threading import Thread
import time


RPC_TIMEOUT_SECONDS = 10


class AppServer:
    def __init__(self, executable, home):
        env = os.environ.copy()
        for name in ("OPENAI_API_KEY", "CODEX_API_KEY"):
            env.pop(name, None)
        env["CODEX_HOME"] = str(home)
        args = [str(executable)]
        if not executable.name.lower().startswith("codex-app-server"):
            args.append("app-server")
        args.extend(["--listen", "stdio://", "-c", "features.plugins=false"])
        self.proc = subprocess.Popen(
            args, cwd=home.parent, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.lines = SimpleQueue()
        self.ids = itertools.count(1)
        self.reader = Thread(target=self.read_output, daemon=True)
        self.reader.start()

    def read_output(self):
        try:
            with self.proc.stdout as stdout:
                for line in stdout:
                    self.lines.put(line)
        finally:
            self.lines.put(None)

    def send(self, message):
        self.proc.stdin.write((json.dumps(message) + "\n").encode("ascii"))
        self.proc.stdin.flush()

    def call(self, method, params):
        request_id = next(self.ids)
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + RPC_TIMEOUT_SECONDS
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                line = self.lines.get(timeout=remaining)
            except Empty:
                break
            if line is None:
                raise RuntimeError(f"App Server exited during {method}")
            message = json.loads(line)
            if message.get("id") == request_id and ("result" in message or "error" in message):
                return message
        raise RuntimeError(f"{method} timed out")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.reader.join(timeout=3)


def result(response):
    if "error" in response:
        error = response["error"]
        raise RuntimeError(f"RPC {error['code']}: {error['message']}")
    return response["result"]


def directory_names(response):
    return [item["fileName"] for item in result(response)["entries"] if item["isFile"]]


def read_file(server, path):
    response = server.call("fs/readFile", {"path": str(path)})
    return base64.b64decode(result(response)["dataBase64"], validate=True)


def escape_names(names):
    return [name.encode("unicode_escape").decode("ascii") for name in names]


def check_file(server, path):
    expected = path.read_bytes()
    names = directory_names(server.call("fs/readDirectory", {"path": str(path.parent)}))
    name_count = names.count(path.name)
    content_matches = read_file(server, path) == expected
    code = int(name_count != 1 or not content_matches)
    return code, {
        "status": "failed" if code else "passed",
        "exact_name_count": name_count,
        "content_matches": content_matches,
    }


def check_collision(server, folder):
    native_name = "bad\ud800.txt"
    replacement_name = "bad\ufffd.txt"
    replacement_file = folder / replacement_name
    replacement_data = b"replacement-character file"
    replacement_file.write_bytes(replacement_data)
    if check_file(server, replacement_file)[0]:
        raise RuntimeError("The genuine U+FFFD filename failed the single-file control")

    replacement_file.unlink()
    native_file = folder / native_name
    native_data = b"unpaired-surrogate file"
    native_file.write_bytes(native_data)
    if os.listdir(folder) != [native_name] or native_file.read_bytes() != native_data:
        raise RuntimeError("Windows did not expose the surrogate-only fixture file")

    listing = server.call("fs/readDirectory", {"path": str(folder)})
    misleading_name = False
    unexpected_listing = False
    if "error" in listing:
        without_sibling = {"status": "listing-rejected"}
    else:
        remaining = sorted(directory_names(listing))
        without_sibling = {"returned_names_escaped": escape_names(remaining)}
        misleading_name = replacement_name in remaining
        unexpected_listing = bool(remaining) and not misleading_name
        if misleading_name:
            read = server.call("fs/readFile", {"path": str(replacement_file)})
            without_sibling["alias_read"] = "rpc-error" if "error" in read else "success"
            if "error" in read:
                without_sibling["rpc_error_code"] = read["error"]["code"]

    replacement_file.write_bytes(replacement_data)
    actual_names = sorted(os.listdir(folder))
    if actual_names != sorted([native_name, replacement_name]) or (
        native_file.read_bytes() != native_data or replacement_file.read_bytes() != replacement_data
    ):
        raise RuntimeError("Windows did not expose the two distinct fixture files")

    response = server.call("fs/readDirectory", {"path": str(folder)})
    details = {
        "actual_names_escaped": escape_names(actual_names),
        "single_file_control_passed": True,
        "without_replacement_sibling": without_sibling,
    }
    if "error" in response:
        valid_file_readable = read_file(server, replacement_file) == replacement_data
        code = 2 if unexpected_listing or not valid_file_readable else int(misleading_name)
        return code, {
            **details,
            "status": "listing-rejected",
            "rpc_error_code": response["error"]["code"],
            "valid_file_readable": valid_file_readable,
        }

    names = sorted(directory_names(response))
    count = names.count(replacement_name)
    details.update(
        returned_names_escaped=escape_names(names),
        replacement_name_count=count,
    )
    if count > 1:
        # Open each returned name exactly as a client would, and keep the
        # directory-listing evidence even if a server also rejects the read.
        reads = [server.call("fs/readFile", {"path": str(folder / name)})
                 for name in names if name == replacement_name]
        targets = []
        for read in reads:
            if "error" in read:
                targets.append("read-error")
                continue
            data = base64.b64decode(result(read)["dataBase64"], validate=True)
            targets.append({
                replacement_data: "replacement-character-file",
                native_data: "unpaired-surrogate-file",
            }.get(data, "unexpected-content"))

        return 1, {
            **details,
            "status": "filename-collision",
            "read_targets": targets,
        }
    if names == [replacement_name] and not unexpected_listing:
        if read_file(server, replacement_file) == replacement_data:
            status = "misleading-single-entry" if misleading_name else "unrepresentable-entry-omitted"
            return int(misleading_name), {**details, "status": status}
    return 2, {**details, "status": "unexpected-listing"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server", type=Path, required=True,
        help="Path to the native Codex CLI executable or codex-app-server executable",
    )
    case = parser.add_mutually_exclusive_group(required=True)
    case.add_argument("--file", type=Path, help="Read a synthetic file and verify its name and bytes")
    case.add_argument("--collision", action="store_true", help="Check the filename alias in issue #60916")
    args = parser.parse_args()
    try:
        if os.name != "nt":
            raise RuntimeError("This probe requires native Windows")
        executable = args.server.resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix="codex-path-", dir=Path.cwd()) as scratch:
            root = Path(scratch)
            home = root / "profile"
            home.mkdir()
            with AppServer(executable, home) as server:
                result(server.call("initialize", {
                    "clientInfo": {"name": "windows-path-compat", "version": "1"}
                }))
                server.send({"method": "initialized"})
                if args.collision:
                    folder = root / "fixture"
                    folder.mkdir()
                    code, details = check_collision(server, folder)
                else:
                    code, details = check_file(server, args.file.resolve(strict=True))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        code, details = 2, {"status": "probe-error", "error": str(error)}
    print(json.dumps(details, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
