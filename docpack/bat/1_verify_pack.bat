@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Pack integrity check - SHA-256 via certutil (no Python needed)
cd /d "%~dp0.."
echo.
echo Pack root: %CD%
if not exist "SHA256SUMS.txt" (
  echo [FAIL] SHA256SUMS.txt not found. Run this from the unpacked pack folder.
  pause
  exit /b 1
)
set /a OKCNT=0
set /a FAILCNT=0
for /f "usebackq tokens=1,* delims= " %%A in ("SHA256SUMS.txt") do (
  set "EXP=%%A"
  set "REL=%%B"
  if "!REL:~0,1!"==" " set "REL=!REL:~1!"
  set "REL=!REL:/=\!"
  if not exist "!REL!" (
    echo [FAIL] missing file: !REL!
    set /a FAILCNT+=1
  ) else (
    set "GOT="
    for /f "skip=1 delims=" %%H in ('certutil -hashfile "!REL!" SHA256 2^>nul') do (
      if not defined GOT set "GOT=%%H"
    )
    set "GOT=!GOT: =!"
    if /i "!GOT!"=="!EXP!" (
      echo [OK]   !REL!
      set /a OKCNT+=1
    ) else (
      echo [FAIL] hash mismatch: !REL!
      echo        expected: !EXP!
      echo        actual:   !GOT!
      set /a FAILCNT+=1
    )
  )
)
echo.
echo RESULT: OK=!OKCNT!  FAIL=!FAILCNT!  ^(manifest itself is not self-hashed^)
if !FAILCNT! GTR 0 (
  echo The pack is damaged or incomplete. Re-download the archive.
) else (
  echo All files match the manifest.
)
echo.
pause
exit /b !FAILCNT!
