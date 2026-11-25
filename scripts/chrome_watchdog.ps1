# Watchdog бота tazon: каждые 5 минут (по расписанию Windows) убивает
# Chrome БОТА (профиль tazon-bot), который висит дольше 30 минут.
# Личный Chrome владельца (другой профиль) не трогается.
# Не зависит от живости процесса бота — работает всегда.

$limit = (Get-Date).AddMinutes(-30)
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'chrome.exe' -and
    $_.CommandLine -like '*tazon-bot*' -and
    $_.CreationDate -lt $limit
} | ForEach-Object {
    try {
        Write-Output ("watchdog: killing chrome " + $_.ProcessId + " (age " + [math]::Round(((Get-Date) - $_.CreationDate).TotalMinutes) + " min)")
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
}
