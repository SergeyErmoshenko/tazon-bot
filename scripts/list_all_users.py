"""Список всех пользователей бота и их товаров (read-only)."""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = sqlite3.connect(r"C:\Users\1\tazon-bot\data\monitor.db")
rows = list(c.execute(
    "SELECT s.chat_id, p.store, COALESCE(p.title, p.url), p.is_out "
    "FROM subscriptions s JOIN products p ON p.id = s.product_id "
    "ORDER BY s.chat_id, p.id"
))
users = list(c.execute(
    "SELECT chat_id, COUNT(*) FROM subscriptions GROUP BY chat_id ORDER BY COUNT(*) DESC"
))
print(f"пользователей: {len(users)}, товаров всего: {len(rows)}")
cur = None
for chat_id, store, title, is_out in rows:
    if chat_id != cur:
        print(f"\n=== chat {chat_id} ===")
        cur = chat_id
    mark = " 🚫закончился" if is_out else ""
    print(f"  [{store}] {title[:70]}{mark}")
