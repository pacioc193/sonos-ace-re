@echo off
rem Offline build of ace.exe with the local MSVC toolset and Windows SDK (no CMake, no network).
rem Usage:  cpp\build.bat            (run from anywhere; output goes to cpp\build\)
rem Optional: set WINSDK=10.0.26100.0 first to pick a specific installed Windows SDK.
setlocal
cd /d "%~dp0"

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo [ERR] vswhere.exe not found. Install Visual Studio or "Build Tools for Visual Studio"
  echo       with the workload "Desktop development with C++".
  exit /b 1
)
set "VSPATH="
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSPATH=%%i"
if not defined VSPATH (
  echo [ERR] No MSVC C++ x64 toolset found. In the Visual Studio Installer add:
  echo       "MSVC v14x - VS C++ x64/x86 build tools". The Windows SDK alone has no compiler.
  exit /b 1
)
echo [INF] Visual Studio: %VSPATH%
call "%VSPATH%\VC\Auxiliary\Build\vcvars64.bat" %WINSDK% >nul || exit /b 1
echo [INF] Windows SDK: %WindowsSDKVersion%

if not exist build mkdir build

echo [INF] building protocol tests...
cl /nologo /std:c++17 /EHsc /W3 /utf-8 tests\test_core.cpp /Fe:build\ace_tests.exe /Fo:build\ || exit /b 1
build\ace_tests.exe || exit /b 1

echo [INF] building ace.exe (C++/WinRT, C++20, static CRT)...
cl /nologo /std:c++20 /EHsc /permissive- /utf-8 /W3 /MT /DNOMINMAX /DWIN32_LEAN_AND_MEAN /D_CRT_SECURE_NO_WARNINGS ^
   app\ace_cli.cpp /Fe:build\ace.exe /Fo:build\ /link windowsapp.lib || exit /b 1

echo.
echo [OK] built %CD%\build\ace.exe
echo      try:  build\ace.exe help
exit /b 0
