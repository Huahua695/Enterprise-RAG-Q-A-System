@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  Push to Gitee + GitHub (one command)
echo ============================================
echo.
"%~dp0backend\.venv\Scripts\python.exe" "%~dp0scripts\push_all.py" %*
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (
  echo [OK] Both remotes are up to date.
) else (
  echo [FAILED] At least one remote failed. exit code %RC%
)
echo.
pause
