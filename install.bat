@echo off
setlocal EnableExtensions
::
:: Enhanced Random Character installer for Melee (Slippi / Dolphin), Windows.
::
:: Usage:  install.bat                  (auto-detect Slippi Dolphin)
::         install.bat "D:\Dolphin\User"  (a specific Dolphin "User" folder)
::
:: Copies the Gecko codeset into GameSettings\ and turns Enable Cheats on.
:: No game files are touched. Idempotent -- safe to re-run.
::

:: ---- locate GALE01r2.ini (repo: dist\, release zip: root)
set "INI=%~dp0dist\GALE01r2.ini"
if not exist "%INI%" set "INI=%~dp0GALE01r2.ini"
if not exist "%INI%" echo error: GALE01r2.ini not found next to install.bat & goto :fail

:: ---- target Dolphin "User" folder: first argument, or the Slippi default
set "USERDIR=%~1"
if "%USERDIR%"=="" set "USERDIR=%APPDATA%\Slippi Launcher\netplay\User"
set "USERDIR=%USERDIR:"=%"
if not exist "%USERDIR%" echo error: Dolphin User folder not found: "%USERDIR%" & echo Pass it explicitly, e.g.  install.bat "D:\Dolphin\User" & goto :fail

echo Installing Enhanced Random Character into "%USERDIR%" ...

:: ---- copy the codeset into GameSettings (back up any existing file once)
set "GS=%USERDIR%\GameSettings"
if not exist "%GS%" mkdir "%GS%"
set "DST=%GS%\GALE01r2.ini"
if exist "%DST%" if not exist "%DST%.erc-backup" copy /y "%DST%" "%DST%.erc-backup" >nul & echo   backup: GALE01r2.ini.erc-backup
copy /y "%INI%" "%DST%" >nul
echo   installed GALE01r2.ini

:: ---- turn on Enable Cheats in Config\Dolphin.ini ([Core])
set "ERC_CFG=%USERDIR%\Config\Dolphin.ini"
if not exist "%ERC_CFG%" (
    echo   note: Dolphin.ini not found -- turn on Config ^> General ^> Enable Cheats yourself
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:ERC_CFG; $l=[System.Collections.Generic.List[string]]([IO.File]::ReadAllLines($p)); $ci=-1; for($i=0;$i -lt $l.Count;$i++){ if($l[$i].Trim().ToLower() -eq '[core]'){ $ci=$i; break } }; if($ci -lt 0){ $l.Add('[Core]'); $l.Add('EnableCheats = True') } else { $f=$false; for($j=$ci+1; $j -lt $l.Count -and -not $l[$j].Trim().StartsWith('['); $j++){ if($l[$j].Trim().ToLower().StartsWith('enablecheats')){ $l[$j]='EnableCheats = True'; $f=$true } }; if(-not $f){ $l.Insert($ci+1,'EnableCheats = True') } }; [IO.File]::WriteAllLines($p,$l)"
    echo   Enable Cheats set in Dolphin.ini
)

echo Done! Launch Melee, go to VS Mode, and tap L on a character to test.
if "%~1"=="" pause
exit /b 0

:fail
if "%~1"=="" pause
exit /b 1
