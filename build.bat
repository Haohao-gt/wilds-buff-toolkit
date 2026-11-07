@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] 构建前端
pushd webapp
call npm run build
popd

echo [2/2] 构建宿主
dotnet build app\WildsBuff.csproj -c Release --nologo

echo 完成：app\bin\Release\net9.0-windows\WildsBuff.exe
