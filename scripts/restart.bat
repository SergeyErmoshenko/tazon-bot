@echo off
rem Надёжный перезапуск бота: убивает ВСЕ python-процессы (на ноуте их создаёт
rem только бот), сбрасывает зависшее состояние задачи планировщика и стартует
rem ровно одну копию.
taskkill /F /T /IM python.exe
schtasks /end /tn tazon-bot
schtasks /run /tn tazon-bot
echo Bot restarted.
