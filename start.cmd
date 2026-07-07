@echo off
REM ExtractApp v3A — set up the venv (first run), run the acceptance suite, write a demo workbook.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment and installing dependencies...
  python -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
) else (
  echo [1/3] Virtual environment present.
)

echo [2/3] Running acceptance suite ^(golden corpus + determinism^)...
set EXTRACTAPP_DISABLE_OCR=1
set EXTRACTAPP_DISABLE_VLM=1
".venv\Scripts\python.exe" -m pytest -q || goto :fail

echo [3/3] Running demo extraction -^> .\out ...
".venv\Scripts\python.exe" demo.py || goto :fail

echo.
echo Done. Generated workbook is in the .\out folder.
endlocal
exit /b 0

:fail
echo.
echo FAILED. See the output above.
endlocal
exit /b 1
