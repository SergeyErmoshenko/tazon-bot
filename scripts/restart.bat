@echo off
rem Надёжный перезапуск бота: убивает ВСЕ python-процессы (на ноуте их создаёт
rem только бот), сбрасывает зависшее состояние задачи планировщика, чистит
rem ОСИРОТЕВШИЕ Chrome бота (по профилю tazon-bot — Chrome владельца не трогается)
rem и стартует ровно одну копию.
taskkill /F /T /IM python.exe
schtasks /end /tn tazon-bot
schtasks /run /tn tazon-bot
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*tazon-bot*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Bot restarted.
