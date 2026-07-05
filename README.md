# PESaWis / PESOS Django Simple

Simple Django app for managing a PES/eFootball league with divisions, calendar, feed, friendly requests, player profiles, standings and tournaments.

## Competition Rules (football / FIFA logic)

**Championship (Leagues → Seasons → Divisions)**
- A division holds up to 12 players.
- The calendar is a real round-robin (circle method): every player plays exactly once per round; double round-robin mirrors home & away legs. Optional kick-off date schedules one round per week.
- At the end of a season: the winner of Division 1 is the champion, the top 2 of each lower division are promoted, and the bottom 2 of each division are relegated. `Apply promotion/relegation` moves the memberships automatically.

**Tournaments ("Kas dial lma" and private cups)**
- The organizer chooses the format: group stage + knockout (default), direct knockout, or a single round-robin league.
- Groups of 4, snake-seeded from player rankings (FIFA pots). Official format plays home & away inside groups; the organizer can pick single round instead.
- Top 2 of each group qualify. With 2/4/8 groups the bracket uses the exact FIFA cross-pairings (A1–B2, B1–A2, …) so group rivals can only meet again in the final. With other group counts, the best third-placed players complete the bracket (Euro style).
- Tied knockout matches are decided by a penalty shoot-out score (or a manual winner). Semi-final losers play a third-place match. The champion is crowned automatically after the final.
- The draw and all fixtures are generated automatically as soon as the tournament is full (or via the "Run Draw" button).

**Live streaming**
- Any player can go live from the Feed (`🔴 Go live`): start screen sharing, switch to eFootball and play, then come back and end the stream. The screen is sent peer-to-peer over WebRTC — the server only relays signaling and nothing is ever recorded or stored.

## Local Installation on Windows

```powershell
cd "C:\Users\PC\Documents\Ayman\PESaWis"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

If `python` is not available globally on Windows, use:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Environment Variables

Local defaults are development-friendly. For production, set:

```bash
export DJANGO_SECRET_KEY="replace-with-a-secure-secret"
export DJANGO_DEBUG=False
```

Before deploying, replace `YOUR_USERNAME.pythonanywhere.com` in `leaguehub/settings.py` with your real PythonAnywhere domain.

## GitHub

Do not commit `.venv/`, `db.sqlite3`, `media/`, `staticfiles/`, `.env`, logs, IDE folders or Python cache files.

```powershell
cd "C:\Users\PC\Documents\Ayman\PESaWis"
git init
git add .
git commit -m "Initial Django league management app"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Replace `USERNAME` and `REPOSITORY` before running the remote commands.

## PythonAnywhere Deployment

In a PythonAnywhere Bash console:

```bash
git clone https://github.com/USERNAME/REPOSITORY.git
cd REPOSITORY
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

## PythonAnywhere Web Tab

1. Create a manual web app.
2. Choose a Python version compatible with Django 5.
3. Set virtualenv path:

```text
/home/USERNAME/REPOSITORY/.venv
```

4. Configure static files:

```text
URL: /static/
Directory: /home/USERNAME/REPOSITORY/staticfiles
```

5. Configure media files:

```text
URL: /media/
Directory: /home/USERNAME/REPOSITORY/media
```

6. Edit the WSGI file.
7. Reload the web app.

## PythonAnywhere WSGI Example

The Django settings module is `leaguehub.settings`.

```python
import os
import sys

path = "/home/USERNAME/REPOSITORY"
if path not in sys.path:
    sys.path.append(path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leaguehub.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Replace `USERNAME` and `REPOSITORY`.

## Static and Media

```powershell
python manage.py collectstatic --noinput
```

Static files are collected into `staticfiles/`. Uploaded files are stored in `media/`. Both folders are ignored by Git.

## Useful Local Checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test
python manage.py runserver
```

If global `python` is unavailable:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver
```

## Main Routes

- `/`
- `/rules/`
- `/feed/`
- `/login/`
- `/signup/`
- `/staff/`
- `/admin/`

## Known Deployment Notes

- This project currently uses SQLite by default.
- `DEBUG` defaults to `True` locally and should be set to `False` on PythonAnywhere.
- The placeholder `YOUR_USERNAME.pythonanywhere.com` must be replaced before production use.
- Media uploads need the `/media/` mapping in PythonAnywhere.
