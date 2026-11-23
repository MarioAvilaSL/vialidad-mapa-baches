@echo off
rem Arranca el motor de rutas GraphHopper. Doble clic o desde PowerShell: .\iniciar_graphhopper.bat
cd /d "%~dp0"

where java >nul 2>nul
if errorlevel 1 (
  echo No se encontro Java. Instala Java 17 o superior ^(Temurin, adoptium.net^) y vuelve a abrir esta ventana.
  pause
  exit /b 1
)

java -version 2>&1 | find "64-Bit" >nul
if errorlevel 1 (
  echo Tu Java es de 32 bits y no puede procesar el mapa de Ecuador ^(no puede usar tanta memoria^).
  echo Desinstala ese Java e instala la version de 64 bits ^(x64^) desde adoptium.net.
  echo Para comprobarlo: java -version debe decir "64-Bit Server VM".
  pause
  exit /b 1
)

set "JAR="
for %%f in (graphhopper-web-*.jar) do set "JAR=%%f"
if not defined JAR (
  echo Falta el archivo graphhopper-web-11.1.jar en esta carpeta. Ver README.md, paso 2.
  pause
  exit /b 1
)

if not exist graph-cache (
  if not exist ecuador-latest.osm.pbf (
    echo Falta el mapa ecuador-latest.osm.pbf en esta carpeta. Ver README.md, paso 3.
    pause
    exit /b 1
  )
  echo Primera vez: se procesa el mapa de Ecuador. Puede tardar varios minutos; no cierres esta ventana.
)

echo Cuando aparezca "Started Server" el motor de rutas esta listo. Para detenerlo cierra esta ventana.
rem Si aparece OutOfMemoryError, sube -Xmx2g a -Xmx3g o -Xmx4g
java -Xmx2g -jar "%JAR%" server config.yml
pause
