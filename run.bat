@echo off
chcp 65001 >nul
title Virtual Office - ออฟฟิศเสมือน
cd /d "%~dp0"

set "PYEXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo ============================================
echo    Virtual Office - ออฟฟิศเสมือน
echo    ทีม AI ช่วยงานคุณคนเดียว
echo ============================================
echo.
echo [+] ตรวจสอบ library...
"%PYEXE%" -m pip install --quiet flask

echo [+] กำลังเริ่มระบบที่ http://localhost:5100
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:5100'"

echo [+] เปิดเบราว์เซอร์ให้อัตโนมัติ (ปิดหน้าต่างนี้ = ปิดระบบ)
echo.
"%PYEXE%" app.py

echo.
echo ระบบหยุดทำงานแล้ว
pause
