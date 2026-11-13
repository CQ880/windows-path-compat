# Windows 路径兼容性测试工具

用同一条测试命令检查 Windows 上的英文、空格、中文、重音字符以及中文与空格组合路径。已在原生 Windows x64 与 Python 3.12.14 实测。命令行工具使用 Python 标准库。

## 快速开始

在 PowerShell 中进入本目录后运行。需要将 `python` 替换成 Python 3.12 的绝对路径时，两处一起替换，并在第一处加 PowerShell 调用符 `&`。

~~~powershell
$probe = (Resolve-Path 'examples/check_text.py').Path
python winpath.py --mode file --fixture examples/sample.txt --json result.json -- python $probe '{input}'
~~~

文件模式共运行十次，分别变更输入文件的父目录和文件名。`'{input}'` 是一个独立参数，由工具替换为样例副本的绝对路径。给样例保留 ASCII 扩展名即可，例如 `.pdf` 或 `.txt`。

工作目录模式共运行五次。把测试脚本放在固定位置，通过绝对路径调用。可以用 `--fixture` 把一个文件复制到各工作目录，并通过 `{input}` 把副本路径传给脚本。

~~~powershell
python winpath.py --mode cwd -- python -c 'import os; print(os.getcwd())'
~~~

工具会启动你提供的程序。测试命令的退出码应反映实际输出是否正确，例如确实解析到一页 PDF。请传入可信的命令和样例。执行入口为原生 Windows 程序，可用 `python -m` 或 `pwsh -File` 启动脚本。调用方脚本需要保持可重复运行，并在完成时退出。

## 读报告与复现

| 退出码 | 含义 |
| --- | --- |
| `0` | 所有运行的检查通过 |
| `1` | 英文对照通过，有路径变体的命令失败 |
| `2` | 存在英文对照失败、无法启动、超时或其他配置与环境问题。报告仍保留已观察到的路径差异。 |

`--timeout` 可设置单次运行超时，默认 30 秒。若系统临时目录含空格或非 ASCII 字符，用 `--root` 指定一个符合条件的可写目录，以保证英文对照路径有效。工具默认清理本次实验目录。排查时加 `--keep` 保留目录，再用 JSON 中的 `cwd` 和 `argv` 重跑对应命令。保留的目录可能包含你提供的样例和测试程序写出的文件。JSON 包含命令参数和 stdout、stderr 的末尾片段，分享前检查内容。

可以给快速开始的命令在 `{input}` 后追加 `--fail-on-unicode`，观察 `path-difference` 和退出码 `1`。

## 实测记录

| 项目 | 原生 Windows 结果 |
| --- | --- |
| docling-parse 7.15.0 | 4/10 通过，6 个含中文或重音字符的父目录或文件名用例失败。 [旧版报告](docling-cli-old.json) |
| docling-parse 7.16.0 | 10/10 通过。 [修复版报告](docling-cli-fixed.json) |
| jq 1.8.2 | 10/10 通过，每组均读到预期字段值。 [jq 报告](jq-cli.json) |

复现 Docling 对照时，在两个隔离的 Python 3.12 环境分别安装 `docling-parse==7.15.0` 与 `docling-parse==7.16.0`，并用 `python examples/make_pdf.py sample.pdf` 生成同一份 PDF。为两个环境分别设置 `$doclingPython` 为对应解释器的绝对路径，执行下列命令并保留各自报告。

~~~powershell
$probe = (Resolve-Path 'examples/check_pdf.py').Path
python winpath.py --mode file --fixture sample.pdf --json docling-result.json -- $doclingPython $probe '{input}'
~~~

预期旧版返回 1，修复版返回 0。 [Docling 修复说明](https://github.com/docling-project/docling-parse/releases/tag/v7.16.0)

## GitHub Actions 接入

在 Windows job 中先 checkout 调用方仓库并配置 Python 3.12，再调用本 Action。测试脚本路径中的 `{workspace}` 由 Action 替换为调用方工作区。示例里的样例文件和测试脚本应位于调用方仓库中。在本仓库测试修改时，可用 `uses: ./`。

~~~yaml
- uses: CQ880/windows-path-compat@v0.1.0
  with:
    mode: file
    fixture: examples/sample.txt
    report: winpath-report.json
    command-json: '["python", "{workspace}/examples/check_text.py", "{input}"]'
~~~

工作流 [smoke.yml](.github/workflows/smoke.yml) 已在 GitHub 托管的 Windows runner 上通过。正常组退出 0，故障组识别出六个 Unicode 路径差异并退出 1，最终断言通过。 [托管运行](https://github.com/CQ880/windows-path-compat/actions/runs/43420519010)

[Docling 示例工作流](.github/workflows/docling-pilot.yml) 可手动运行，在 Windows 上对照 7.15.0 和 7.16.0，验证 PDF 页数与路径差异。维护者可以用同样的接入方式检查自己发布的 Windows 构建。

## Codex App Server 路径检查

[Codex 探针](examples/check_codex_paths.py) 通过本地 stdio 调用 `fs/readDirectory` 和 `fs/readFile`。在 Windows 上，用官方发行版的 App Server 或本机 Codex CLI 即可运行。探针使用临时配置目录，测试请求均在本地执行，无需账号或 API 密钥。 [Codex App Server 文档](https://learn.chatgpt.com/docs/app-server#filesystem)

在工具目录中用 PowerShell 运行。先把 `$server` 改为已下载的可执行文件路径。默认临时目录不满足英文对照条件时，给 `winpath.py` 加上 `--root` 并指定已有的英文无空格目录。

~~~powershell
$server = (Resolve-Path 'C:/codex/codex-app-server-x86_64-pc-windows-msvc.exe').Path
$probe = (Resolve-Path 'examples/check_codex_paths.py').Path
python winpath.py --mode file --fixture examples/sample.txt --timeout 40 --json codex-paths.json -- python $probe --server $server --file '{input}'
python $probe --server $server --collision
~~~

官方 App Server 0.169.0 的常规路径矩阵通过 10/10。特殊用例在支持此类原生文件名的卷上创建两个文件，一个文件名包含未配对 UTF-16 代理码元，另一个包含 U+FFFD。测试版将两者列为同名，按返回名称读取会得到 U+FFFD 文件。碰撞用例退出码 `1` 表示发现误导性名称，`0` 表示接口明确拒绝该目录列表或省略了无法表示的条目，`2` 表示未获得可判定结果。 [上游 Issue #60916](https://github.com/openai/codex/issues/60916)

英文使用说明见 [README.en.md](README.en.md)。

本项目采用 [MIT 许可证](LICENSE)。
