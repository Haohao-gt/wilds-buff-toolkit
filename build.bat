@echo off
cd /d "%~dp0.."
"C:\Windows\Microsoft.NET\Framework4.0.30319\csc.exe" /nologo /target:winexe /out:dist\BuffTool.exe /r:System.Windows.Forms.dll /r:System.Drawing.dll tools\BuffTool.cs
