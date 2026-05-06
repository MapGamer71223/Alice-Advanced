@echo off

REM ---- ACTIVATE CONDA ENVIRONMENT ----
call "%USERPROFILE%\miniconda3\Scripts\activate.bat" alice311

REM ---- START OLLAMA SERVER IN A SEPARATE CMD WINDOW ----
start "" cmd /k "ollama serve"

REM ---- WAIT 3 SECONDS FOR OLLAMA TO BOOT ----
timeout /t 3 >nul

REM ---- RUN ALICE ----
cd /d "C:\Users\punya\Project\alice\core"
python main.py

pause
