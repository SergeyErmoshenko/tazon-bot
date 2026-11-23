"""Прицельное убийство Chrome БОТА: только процессы с user-data-dir внутри tazon-bot.

Личный Chrome владельца (со своим профилем) не трогается.
Запуск на ноутбуке: .venv\\Scripts\\python.exe -X utf8 scripts\\kill_bot_chrome.py
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PS = r"""
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'chrome.exe' -and $_.CommandLine -match 'tazon-bot'
} | ForEach-Object {
    Write-Output ('killing ' + $_.ProcessId)
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
"""

r = subprocess.run(["powershell", "-NoProfile", "-Command", PS], capture_output=True, text=True)
print(r.stdout or "(no output)")
leftover = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"], capture_output=True, text=True)
print("chrome left:", leftover.stdout.count("chrome.exe"))
