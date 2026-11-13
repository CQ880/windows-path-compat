$ErrorActionPreference = 'Stop'

try {
    $commandArgs = ConvertFrom-Json -InputObject $env:WINPATH_COMMAND -NoEnumerate
    if ($commandArgs -isnot [array] -or $commandArgs.Count -eq 0) {
        throw 'command-json must be a nonempty JSON array'
    }
    foreach ($arg in $commandArgs) {
        if ($arg -isnot [string]) { throw 'Every command-json item must be a string' }
    }
    $options = @('--mode', $env:WINPATH_MODE, '--timeout', $env:WINPATH_TIMEOUT)
    if ($env:WINPATH_FIXTURE) { $options += @('--fixture', $env:WINPATH_FIXTURE) }
    if ($env:WINPATH_ROOT) { $options += @('--root', $env:WINPATH_ROOT) }
    if ($env:WINPATH_REPORT) { $options += @('--json', $env:WINPATH_REPORT) }
    # Expand the caller workspace before the CLI varies cwd.
    $callerWorkspace = if ($env:GITHUB_WORKSPACE) { $env:GITHUB_WORKSPACE } else { (Get-Location).Path }
    $commandArgs = @($commandArgs | ForEach-Object { $_.Replace('{workspace}', $callerWorkspace) })
    $PSNativeCommandArgumentPassing = 'Standard'
    $PSNativeCommandUseErrorActionPreference = $false
    & python (Join-Path $PSScriptRoot 'winpath.py') @options '--' @commandArgs
    $resultCode = $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    $resultCode = 2
}
if ($env:GITHUB_OUTPUT) {
    "exit-code=$resultCode" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
}
exit $resultCode
