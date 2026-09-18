@echo off
cd /d "%~dp0"
start "" http://127.0.0.1:7712
python client\server.py --port 7712
pause
