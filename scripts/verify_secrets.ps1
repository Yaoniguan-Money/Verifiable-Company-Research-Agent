$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ignoredPathPattern = "\\(\.git|\.venv|node_modules|dist|\.pytest_cache|\.ruff_cache)\\"
$failed = $false

if (Test-Path -LiteralPath ".git") {
    $candidatePaths = git ls-files --cached --others --exclude-standard
    if ($LASTEXITCODE -ne 0) {
        Write-Error "git file listing failed."
        exit 1
    }
} else {
    $candidatePaths = Get-ChildItem -Recurse -File -Force |
        Where-Object { $_.FullName -notmatch $ignoredPathPattern } |
        ForEach-Object { Resolve-Path -Relative $_.FullName }
}

$envFiles = $candidatePaths |
    Where-Object {
        $name = Split-Path -Leaf $_
        $name -like ".env*" -and $name -ne ".env.example" -and $name -ne ".env.providers.example"
    }

if ($envFiles) {
    Write-Error "Disallowed env files would be included in git:`n$($envFiles -join "`n")"
    $failed = $true
}

$privateCaseFiles = $candidatePaths |
    Where-Object { $_ -match "(^|[\\/])data[\\/]eval[\\/].*(local|private).*\.json$" }

if ($privateCaseFiles) {
    Write-Error "Local/private evaluation case files would be included in git:`n$($privateCaseFiles -join "`n")"
    $failed = $true
}

$secretPatterns = @(
    "sk-[A-Za-z0-9_-]{16,}",
    "bce-v3/[A-Za-z0-9_./+=-]{16,}",
    "AKIA[0-9A-Z]{16}",
    "xox[baprs]-[A-Za-z0-9-]{16,}",
    "^\s*(export\s+)?(DEEPSEEK_API_KEY|QIANFAN_API_KEY|BAIDU_AI_SEARCH_API_KEY|EMBEDDING_API_KEY|DASHSCOPE_API_KEY|API_KEY)\s*=\s*[A-Za-z0-9_./+=-]{8,}"
)

$files = $candidatePaths |
    Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
    ForEach-Object { Get-Item -LiteralPath $_ }

foreach ($pattern in $secretPatterns) {
    $matches = $files | Select-String -Pattern $pattern -CaseSensitive
    if ($matches) {
        Write-Error "Potential secret pattern found for '$pattern':`n$(
            ($matches | ForEach-Object { "$($_.Path):$($_.LineNumber)" }) -join "`n"
        )"
        $failed = $true
    }
}

if (Test-Path -LiteralPath ".git") {
    $history = git log --all --name-only --pretty=format: -- .env ".env.*"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "git history scan failed."
        $failed = $true
    }

    $disallowedHistory = $history |
        Where-Object { $_ -and $_ -ne ".env.example" -and $_ -ne ".env.providers.example" } |
        Sort-Object -Unique
    if ($disallowedHistory) {
        Write-Error "A real env file appears in git history:`n$($disallowedHistory -join "`n")`nRotate exposed keys and rewrite history before opening source."
        $failed = $true
    }
} else {
    Write-Host "No .git directory found; skipped git history scan."
}

if ($failed) {
    exit 1
}

Write-Host "Secret hygiene check passed."
