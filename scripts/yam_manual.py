"""Видимый Chrome с профилем бота на карточке Яндекс Маркета — для ручного прохода капчи.

Запуск на ноутбуке: .venv\\Scripts\\python.exe -X utf8 scripts\\yam_manual.py [url]
По умолчанию — тестовая карточка. Окно остаётся открытым, пока не нажмёте Enter в консоли.
"""
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\1\tazon-bot")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bot import config  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://market.yandex.ru/card/naushniki-nakladnyye-besprovodnyye-ergolux-"
    "bthp01-c02-fm-mp3-mikrofon-chernyye-korobka-15355/6041984286"
)

proc = subprocess.Popen([
    config.CHROME_PATH,
    "--remote-debugging-port=9222",
    f"--user-data-dir={config.BROWSER_PROFILE_DIR}",
    "--window-size=1280,900",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--no-first-run",
    URL,
])
print("Chrome открыт на карточке Маркета (профиль бота).")
print("Пройди капчу, убедись что страница товара открылась, затем нажми Enter здесь.")
try:
    input()
except EOFNotFoundError:
    time.sleep(600)
proc.terminate()
print("Chrome закрыт. Куки капчи сохранены в профиле бота.")
