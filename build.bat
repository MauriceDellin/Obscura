@echo off
REM ============================================================
REM  Build-Skript: erzeugt Icon + EXE (+ optional Installer)
REM  Doppelklick oder in PowerShell/CMD ausfuehren.
REM ============================================================
setlocal
cd /d "%~dp0"

set PY=py -3.13
where py >nul 2>nul || set PY=python

echo.
echo [1/4] Benoetigte Pakete installieren...
%PY% -m pip install --upgrade pyinstaller pillow pytesseract || goto :error

echo.
echo [2/4] App-Icon erzeugen (app.ico)...
%PY% make_icon.py || goto :error

echo.
echo [3/4] EXE bauen mit PyInstaller...
%PY% -m PyInstaller --noconfirm --clean anonymize.spec || goto :error
echo     -^> dist\Obscura.exe

echo.
echo [4/4] Installer bauen (Inno Setup, falls vorhanden)...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    "%ISCC%" installer.iss || goto :error
    echo     -^> Output\Obscura-Setup.exe
) else (
    echo     Inno Setup nicht gefunden - Installer-Schritt uebersprungen.
    echo     Inno Setup: https://jrsoftware.org/isdl.php
    echo     Danach erneut ausfuehren oder "ISCC.exe installer.iss" aufrufen.
)

echo.
echo Fertig.
goto :end

:error
echo.
echo FEHLER beim Build - siehe Ausgabe oben.
exit /b 1

:end
endlocal
pause
