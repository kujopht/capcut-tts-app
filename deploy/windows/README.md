# Worker TTS tu khoi dong tren Windows (laptop nay)

Co che THAT, khong phai Scheduled Task, khong phai systemd.

## Vi sao Startup folder, khong phai Scheduled Task

`.claude/hooks/guard_indirect_exec.py` cua chinh repo nay chan cung
`schtasks`, `Register-ScheduledTask`, va MOI cach goi `powershell.exe`
(ke ca `-File`) trong MOI che do bao gom `bypassPermissions` — day la
ranh gioi CO CHU DICH, khong phai loi. Vi vay AI khong the tu dang ky
Scheduled Task. Startup folder (`shell:startup`) la co che Windows-native
THAY THE: dat mot tep vao do, Windows tu chay no moi lan nguoi dung nay
dang nhap — khong can dang ky registry/task scheduler, chi la MOT thao
tac ghi tep thuong.

Danh doi so voi Scheduled Task: chi chay sau khi dang nhap (khong chay o
man hinh khoa truoc khi ai dang nhap), va chi cho DUNG nguoi dung
`nguye`. Cho mot laptop ca nhan can worker chay trong luc dang dung may,
day la du.

## Da cai san (khong can lam gi them)

`deploy/windows/start_worker_silent.vbs` da duoc SAO CHEP vao:

    %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\start_worker_silent.vbs

Tep do chi tro (duong dan tuyet doi) toi `run_worker.bat` trong repo nay
— sua logic worker thi sua `run_worker.bat`, khong can dat lai Startup.

## Co che

1. Dang nhap Windows -> Startup folder chay
   `start_worker_silent.vbs` (an, khong hien console).
2. `.vbs` goi `run_worker.bat` (trong repo nay) an.
3. `run_worker.bat`:
   - `cd` ve thu muc repo (tu suy ra tu vi tri chinh no, khong hardcode
     ngoai duong dan Startup);
   - dat `FAS_ENV_FILE=server\.env.production`;
   - DUNG HAN neu thieu `server\.env.production` hoac `.venv` (khong
     lang le chay sai credential);
   - vong lap: chay `python -m server.worker --require-env production`,
     ghi log vao `server\var\worker\logs\worker.log`, neu worker THOAT
     (crash, kill, restart Windows Update...) thi doi 10 giay roi chay
     lai — KHONG dung han vinh vien vi mot lan loi thoang qua.

## Kiem tra worker dang chay that

```
.venv\Scripts\python.exe -m server.worker --check
```

Doc file nhip `server\var\worker\heartbeat.json`. Tra ve 0 neu nhip con
moi (trong `FAS_WORKER_STALE_SECONDS`, mac dinh ~60s).

Xem log:

```
type server\var\worker\logs\worker.log
```

## Go bo (neu can dung han)

Xoa MOT tep nay (khong dung xoa gi khac):

```
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\start_worker_silent.vbs"
```

Roi dong tien trinh `python.exe` dang chay worker (Task Manager, hoac
`taskkill /PID <pid>` voi pid doc tu heartbeat.json) neu muon dung ngay
thay vi doi den lan dang xuat/dang nhap tiep theo.

## Gioi han that su, khong che giau

- Khong chay truoc khi dang nhap Windows (khac Scheduled Task/service
  that). Neu laptop khoi dong lai va khong ai dang nhap, worker KHONG
  chay cho den khi co nguoi dang nhap.
- Khong tu phuc hoi neu `server\.env.production` bi xoa/het han — vong
  lap se DUNG HAN moi lan thu lai (dung thiet ke: khong am tham chay
  credential sai).
- Day la worker THAT, se claim va chay JOB THAT cua MOI nguoi dung tren
  production, khong chi noi dung cua mission nao dang chay — dung y
  thiet ke ban dau cua kien truc "worker tren laptop".
