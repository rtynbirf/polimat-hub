@echo off
setlocal EnableExtensions
title fetch_models - download NLLB + whisper-tiny to .\models
cd /d "%~dp0"

if not exist "tools\fetch_models.py" (
  echo [FAIL] tools\fetch_models.py not found next to this bat.
  echo Keep the kit intact: this bat and the "tools" folder must stay together.
  pause
  exit /b 1
)

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [FAIL] Python not found. Install from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH" in the installer, then run this bat again.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Python launcher: %PY%
echo Downloading: mt = NLLB-200 translator (~850 MB) + asr-tiny = whisper-tiny (~40 MB)
echo Destination: models\  HF revision is pinned into models\MANIFEST.sha256 on first
echo run; re-runs continue where they stopped, strictly at the same pinned revision.
echo Needs: internet to huggingface.co, ~1 GB free disk, no pip installs.
echo.
%PY% tools\fetch_models.py --set mt asr-tiny
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (
  echo RESULT: OK - models are in .\models , manifest: models\MANIFEST.sha256
  echo Offline test: disconnect the internet, open the player, translate a line.
) else (
  echo RESULT: FAIL rc=%RC% - just re-run this bat: it continues where it stopped.
  echo If huggingface.co is unreachable from your network - try later or via VPN.
)
pause
exit /b %RC%
