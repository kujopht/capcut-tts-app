' Chay run_worker.bat AN (khong hien cua so console) khi Windows dang nhap.
' Ban than tep .vbs nay duoc dat trong Startup folder cua Windows
' (%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup) boi
' scripts/recover_worker_env_production.py's sibling install step -- xem
' deploy/windows/README.md. Logic that nam trong run_worker.bat (theo doi
' git); tep nay chi la mot con tro tuyet doi toi do, de cap nhat
' run_worker.bat khong can dat lai Startup.

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Users\nguye\Documents\CapCut-TTS-App\deploy\windows\run_worker.bat""", 0, False
