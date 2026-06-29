# PESaWis / PESOS Django Simple

Simple Django app for managing a PES/eFootball league with divisions, calendar, feed, friendly requests, player profiles, standings and tournaments.

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
