# scan_tokens.ps1 - find LIVE GitHub tokens in text files.
# ASCII-only on purpose: parses identically under any Windows codepage.
param([string]$Root = ".")
$patterns = @(
  'ghp_[0-9A-Za-z]{36}',
  'gho_[0-9A-Za-z]{36}',
  'ghu_[0-9A-Za-z]{36}',
  'ghs_[0-9A-Za-z]{36}',
  'ghr_[0-9A-Za-z]{36}',
  'github_pat_[0-9A-Za-z_]{60,}'
)
$regex = ($patterns -join '|')
$exts = @('*.md', '*.txt', '*.json', '*.csv', '*.patch', '*.ps1')
$files = Get-ChildItem -Path $Root -Recurse -File -Include $exts |
         Where-Object { $_.FullName -notmatch '\\\.git\\' }
$checked = 0
$hits = 0
foreach ($f in $files) {
  $checked++
  $m = Select-String -Path $f.FullName -Pattern $regex -AllMatches
  if ($m) {
    foreach ($line in $m) {
      Write-Output ("[REAL TOKEN] " + $f.FullName + " : line " + $line.LineNumber)
      $hits += $line.Matches.Count
    }
  }
}
Write-Output ("Files scanned: " + $checked)
Write-Output ("Real tokens found: " + $hits)
if ($hits -gt 0) { exit 1 } else { exit 0 }
