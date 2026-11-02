@echo off
rem Start SLD Designer (opens your browser). Needs:  pip install -r requirements.txt
cd /d "%~dp0"
python -m sld_designer %*
