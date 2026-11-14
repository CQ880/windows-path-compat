# Windows Path Compatibility Tests

Run an existing test command across Windows paths with spaces, Chinese characters, accented Latin characters, or a mix of Chinese characters and spaces. The tool uses the Python standard library. The local test environment is native Windows x64 with Python 3.12.14.

From this directory in PowerShell, run

~~~powershell
$probe = (Resolve-Path 'examples/check_text.py').Path
python winpath.py --mode file --fixture examples/sample.txt --json result.json -- python $probe '{input}'
~~~

File mode runs ten cases across two scenarios. One changes the input file's parent directory, and the other changes its name. The tool replaces the separate `{input}` argument with the absolute path to the fixture copy. Use an ASCII extension such as `.pdf` or `.txt` for the fixture. Working-directory mode runs five cases. It can also copy a fixture into each working directory.

~~~powershell
python winpath.py --mode cwd -- python -c 'import os; print(os.getcwd())'
~~~

Use a trusted executable and fixture. Pass a test command that checks the actual output and exits nonzero when the check fails. Use an absolute script path with an explicit interpreter such as Python or PowerShell. If the Windows temp path contains spaces or non-ASCII characters, pass an existing writable ASCII directory without spaces via `--root`.

| Exit code | Meaning |
| --- | --- |
| `0` | All cases passed |
| `1` | A path variant failed with its ASCII control passing |
| `2` | An incomplete or invalid run, such as a failing control, a timeout, or a launch error |

Add `--keep` before the `--` separator to retain case files and replay using the report's `cwd` and `argv`. The JSON report contains command arguments and tails of child output. Review those fields before sharing the file.

The Docling reports show the original Unicode path failure in [7.15.0](docling-cli-old.json) and the passing run in [7.16.0](docling-cli-fixed.json). The [jq 1.8.2 report](jq-cli.json) records ten passing file checks with an assertion on the parsed value.

For GitHub Actions, check out the caller repository and set up Python 3.12 in a Windows job before calling the composite action. Provide the command as a JSON array. The action expands `{workspace}` in arguments to the caller's workspace. The [example workflow](.github/workflows/smoke.yml) passed on a GitHub-hosted Windows runner. It verified exit 0 for the healthy probe and exit 1 with six path differences for the deliberately failing probe. [Hosted run](https://github.com/CQ880/windows-path-compat/actions/runs/43420519010)

Point the action at a fixture and test script checked into your repository.

~~~yaml
- uses: CQ880/windows-path-compat@v0.1.0
  with:
    mode: file
    fixture: examples/sample.txt
    report: winpath-report.json
    command-json: '["python", "{workspace}/examples/check_text.py", "{input}"]'
~~~

Run the [Docling example workflow](.github/workflows/docling-pilot.yml) manually to compare versions 7.15.0 and 7.16.0 on Windows. It checks the parsed page count and the known path regression. Adapt the same pattern to test your own Windows builds.

## Codex App Server path checks

The [Codex probe](examples/check_codex_paths.py) calls `fs/readDirectory` and `fs/readFile` over local stdio with a temporary Codex configuration directory. Use the native Codex CLI or the standalone App Server on Windows. The filesystem requests require no account or API key. [App Server filesystem documentation](https://learn.chatgpt.com/docs/app-server#filesystem)

Run from this repository in PowerShell. Set `$server` to the executable you want to test. If the system temp path has spaces or non-ASCII characters, use `--root` to pass an existing writable path without them.

~~~powershell
$server = (Resolve-Path 'C:/codex/codex-app-server-x86_64-pc-windows-msvc.exe').Path
python codex_regression.py --server $server --report codex-regression.json
~~~

The report records the Codex version, path matrix, and filename collision result. Exit `0` means the ordinary paths passed and the check found no misleading filename, `1` means a path difference or misleading filename was observed, and `2` means the result was incomplete. Run `python examples/check_codex_paths.py --server $server --collision` to check the collision on its own.

Official App Server 0.169.0 passed all ten ordinary path checks locally. On NTFS, a native filename with an unpaired UTF-16 surrogate was returned as U+FFFD, colliding with an existing name. Reading that name returned the other file's bytes. Dispatch the [Codex workflow](.github/workflows/codex-paths.yml) to verify this baseline on a hosted Windows runner using the pinned official release. [Upstream issue #60916](https://github.com/openai/codex/issues/60916)

This project uses the [MIT license](LICENSE).
