param(
    [string]$Version = "0.1.1"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDirectory = Join-Path $Root "release"
$Archive = Join-Path $ReleaseDirectory "aix-open-v$Version.zip"

Push-Location $Root
try {
    python -m pytest --cov=aix --cov-fail-under=80
    python -m build
    aix validate examples\paper_worked_example.yaml
    aix score examples\paper_worked_example.yaml

    New-Item -ItemType Directory -Force $ReleaseDirectory | Out-Null
    if (Test-Path -LiteralPath $Archive) {
        Remove-Item -LiteralPath $Archive -Force
    }
    $Items = @(
        ".github", "docs", "examples", "notebooks", "papers", "rubrics", "scripts", "spec",
        "src", "tests", ".gitignore", "CHANGELOG.md", "CITATION.cff",
        "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "LICENSE", "MANIFEST.in",
        "pyproject.toml", "README.md", "SECURITY.md"
    )
    Compress-Archive -Path $Items -DestinationPath $Archive -CompressionLevel Optimal
    Write-Output $Archive
}
finally {
    Pop-Location
}
