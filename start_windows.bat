@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 goto no_python

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python environment...
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    py -3.12 -m venv .venv
  ) else (
    py -3.13 -c "import sys" >nul 2>nul
    if errorlevel 1 goto unsupported_python
    py -3.13 -m venv .venv
  )
  if errorlevel 1 goto failed
)

echo Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo Starting Following blowing at http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py
goto end

:no_python
echo Python Launcher was not found.
echo Install Python 3.12 or 3.13 from python.org and enable "Add Python to PATH".
goto failed

:unsupported_python
echo Python 3.12 or 3.13 was not found.
echo Install a supported version from python.org and try again.
goto failed

:failed
echo.
echo Setup or startup failed. Review the message above.
pause
exit /b 1

:end
endlocal
