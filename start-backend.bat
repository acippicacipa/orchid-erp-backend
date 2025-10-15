@echo off
echo "Starting Backend Server..."
start "Backend" cmd /k "venv\Scripts\activate && python manage.py runserver 0.0.0.0:8000"
