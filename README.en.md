# Windows Path Compatibility Tests

Run an existing test command across Windows paths with spaces, Chinese characters, accented Latin characters, or a mix of Chinese characters and spaces. The tool uses the Python standard library. The local test environment is native Windows x64 with Python 3.12.14.

To reproduce the Codex filename or search issues, see [Codex App Server regression checks](#codex-app-server-regression-checks).

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
- uses: CQ880/windows-path-compat@v0.2.0
  with:
    mode: file
    fixture: examples/sample.txt
    report: winpath-report.json
    command-json: '["python", "{workspace}/examples/check_text.py", "{input}"]'
~~~

Run the [Docling example workflow](.github/workflows/docling-pilot.yml) manually to compare versions 7.15.0 and 7.16.0 on Windows. It checks the parsed page count and the known path regression. Adapt the same pattern to test your own Windows builds.

## Codex App Server regression checks

The [Codex probe](examples/check_codex_paths.py) calls the directory listing, file read, and file search APIs over local stdio. Use the native Codex CLI or standalone App Server on Windows. The probe uses synthetic files and a temporary configuration directory and needs no account or API key. [App Server documentation](https://learn.chatgpt.com/docs/app-server)

Run from this repository in PowerShell. Set `$server` to the executable you want to test. If the system temp path has spaces or non-ASCII characters, use `--root` to pass an existing writable path without them.

~~~powershell
$server = (Resolve-Path 'C:/codex/codex-app-server-x86_64-pc-windows-msvc.exe').Path
python codex_regression.py --server $server --report codex-regression.json
~~~

The JSON report records the Codex version, case results, and the filenames each search query found or missed. Exit `0` means the checks passed, `1` indicates an observed path difference, and `2` indicates an incomplete run. Point the same command at a candidate executable to verify a fix.

Official App Server 0.169.0 produced the same results locally and on GitHub-hosted Windows Server 2025.

| Check | Observed result |
| --- | --- |
| Ordinary file paths | 10/10 passed with the original filenames and contents. |
| Filename collision | The server listed two distinct files under one name. Both reads returned the file containing U+FFFD in its name. [Codex #60916](https://github.com/openai/codex/issues/60916) |
| Equivalent Unicode queries | The ASCII control found all 3 files. The precomposed query (NFC) found 1 accented filename, and the decomposed query (NFD) found 2. [Codex #61022](https://github.com/openai/codex/issues/61022) |

Dispatch the workflow to replay the baseline against the pinned build. Run `python examples/check_codex_paths.py --server $server --search` to check search on its own. [Codex workflow](.github/workflows/codex-paths.yml) · [Hosted run](https://github.com/CQ880/windows-path-compat/actions/runs/44023836322) · [Hosted JSON](codex-regression-hosted-0.169.0.json)

This project uses the [MIT license](LICENSE).
