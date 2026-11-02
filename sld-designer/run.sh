#!/usr/bin/env sh
# Start SLD Designer (opens your browser). Needs:  pip install -r requirements.txt
cd "$(dirname "$0")" && exec python3 -m sld_designer "$@"
