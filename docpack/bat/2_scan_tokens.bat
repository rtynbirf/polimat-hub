@echo off
setlocal EnableExtensions
title Token scan - LIVE GitHub tokens only (full pattern with tail)
cd /d "%~dp0.."
echo.
echo Scanning text files for LIVE GitHub tokens.
echo Pattern DESCRIPTIONS inside the docs use bare prefixes or [classes]
echo right after the prefix, so the full-pattern regex filters them out.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "bat\scan_tokens.ps1" -Root "."
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (
  echo RESULT: PASS - no live tokens in the pack.
) else (
  echo RESULT: FAIL - live token found. Revoke it, then rebuild the pack.
)
echo.
pause
exit /b %RC%
