$repoRoot = (Get-Location).Path
$output   = Join-Path $repoRoot 'repo_dump.txt'
$skipExt  = @('.gif', '.jpg', '.jpeg')

Get-ChildItem -Recurse -File | Where-Object {
    $rel   = $_.FullName.Substring($repoRoot.Length).TrimStart('\')
    $parts = $rel -split '\\'
    ($_.FullName -ne $output) -and
    ($_.Name -ne '.gitignore') -and
    ($skipExt -notcontains $_.Extension.ToLower()) -and
    -not (
        ($parts[0] -eq '.git') -or
        ($parts[0] -eq 'venv') -or
        ($parts -contains '__pycache__')
    )
} | ForEach-Object {
    "===== $($_.FullName) ====="
    Get-Content -LiteralPath $_.FullName -Raw
    ""
} | Set-Content -Encoding UTF8 $output
