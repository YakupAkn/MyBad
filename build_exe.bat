@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   MyBad EXE builder (3 files)
echo ============================================
echo.
echo Working folder:
echo %CD%
echo.

if /i not "%~1"=="KEEP" (
  cmd /k "%~f0" KEEP
  exit /b
)

echo [check] Python launcher...
where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: "py" not found. Install Python 3 and enable "py launcher".
  goto END
)
py --version
echo.

echo [check] Source files...
if not exist "mybad.py" (
  echo ERROR: mybad.py missing in this folder.
  goto END
)
if not exist "mybad_gui.py" (
  echo ERROR: mybad_gui.py missing in this folder.
  goto END
)
if not exist "indirme_yardimcisi.py" (
  echo ERROR: indirme_yardimcisi.py missing in this folder.
  goto END
)
echo OK: source files found.
echo.

echo [0/3] Installing / updating PyInstaller...
py -m pip install -U pyinstaller
if errorlevel 1 (
  echo ERROR: pip / PyInstaller failed.
  goto END
)
echo.

echo [1/3] Building MyBad-Console.exe ...
py -m PyInstaller --noconfirm --clean --onefile --console --name MyBad-Console mybad.py
if errorlevel 1 (
  echo ERROR: Console build failed.
  goto END
)
echo OK: Console
echo.

echo [2/3] Building MyBad-GUI.exe ...
py -m PyInstaller --noconfirm --clean --onefile --windowed --name MyBad-GUI --hidden-import mybad --add-data "mybad.py;." mybad_gui.py
if errorlevel 1 (
  echo ERROR: GUI build failed.
  goto END
)
echo OK: GUI
echo.

echo [3/3] Building MyBad-Indir.exe ...
py -m PyInstaller --noconfirm --clean --onefile --windowed --name MyBad-Indir indirme_yardimcisi.py
if errorlevel 1 (
  echo ERROR: Downloader build failed.
  goto END
)
echo OK: Indir
echo.

echo ============================================
echo   DONE
echo ============================================
if exist "dist\MyBad-Console.exe" echo   dist\MyBad-Console.exe
if exist "dist\MyBad-GUI.exe"     echo   dist\MyBad-GUI.exe
if exist "dist\MyBad-Indir.exe"   echo   dist\MyBad-Indir.exe
echo.
echo Upload these 3 files as separate GitHub Release assets.
echo.

:END
echo.
echo Window will stay open. Type exit to close.
echo.
endlocal
