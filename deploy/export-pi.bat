@echo off
setlocal
cd /d "%~dp0.."
set "DEST=dist\FileServe-pi"
if exist "%DEST%" rmdir /s /q "%DEST%"
mkdir "%DEST%"
robocopy . "%DEST%" /E /XD .venv data .git dist tests .cursor __pycache__ .pytest_cache /XF .env *.pyc >nul
echo Wrote %DEST%
endlocal
