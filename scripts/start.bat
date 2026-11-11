@echo off
rem Запуск бота: Ozon price monitor
chcp 65001 >nul
cd /d "%~dp0.."
if not exist .env (
    echo [!] Нет .env — скопируй .env.example в .env и заполни BOT_TOKEN и ADMIN_CHAT_ID
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m bot.main
if errorlevel 1 pause
