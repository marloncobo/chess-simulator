@echo off
setlocal
rem Ejecutar desde Windows. KINOVA_WSL_DISTRO permite elegir otra distribucion.
if not defined KINOVA_WSL_DISTRO set "KINOVA_WSL_DISTRO=Ubuntu-22.04"
pushd "%~dp0"
wsl.exe -d %KINOVA_WSL_DISTRO% -- bash ./simular_brazo_wsl.sh %*
set "RESULT=%ERRORLEVEL%"
popd
echo La sesion termino con codigo %RESULT%.
if not "%RESULT%"=="0" (
  echo La simulacion termino con codigo %RESULT%.
  pause
)
exit /b %RESULT%
