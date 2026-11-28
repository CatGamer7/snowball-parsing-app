@echo off
setlocal
chcp 65001 >nul
set "SNOWBALL_ROOT=%~dp0"
if not exist "%SNOWBALL_ROOT%backend\.venv\Scripts\python.exe" (
    echo [SnowBall] Missing working backend environment: backend\.venv
    pause
    exit /b 1
)
"%SNOWBALL_ROOT%backend\.venv\Scripts\python.exe" -u "%SNOWBALL_ROOT%build_tools\build_windows.py" %*
set "SNOWBALL_EXIT=%ERRORLEVEL%"
if not "%SNOWBALL_EXIT%"=="0" pause
exit /b %SNOWBALL_EXIT%
