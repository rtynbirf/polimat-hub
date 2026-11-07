@echo off
setlocal EnableExtensions
title POLIMAT PACK v2.1 - launcher
cd /d "%~dp0"

:menu
cls
echo ==============================================================
echo  POLIMAT PACK v2 - action menu
echo  Tool output is English on purpose: these scripts are pure
echo  ASCII, so no Windows codepage (866/1251/65001) can break them.
echo  All Russian explanations: 00_README_FIRST.txt and *.md docs.
echo ==============================================================
echo  [1] Verify pack integrity  - SHA-256 vs SHA256SUMS.txt
echo  [2] Scan pack texts for LIVE GitHub tokens
echo  [3] Open 00_README_FIRST.txt in Notepad
echo  [4] List pack files
echo  [0] Exit
echo.
choice /c 12340 /n /m "Select: "
if errorlevel 5 goto end
if errorlevel 4 goto list
if errorlevel 3 goto readme
if errorlevel 2 goto scan
if errorlevel 1 goto verify

:verify
call "bat\1_verify_pack.bat"
goto menu
:scan
call "bat\2_scan_tokens.bat"
goto menu
:readme
start notepad "00_README_FIRST.txt"
goto menu
:list
dir /o:n
echo.
pause
goto menu
:end
endlocal
