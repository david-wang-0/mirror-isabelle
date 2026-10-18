#!/bin/sh
# Test suite for multi-parent sessions and the proof cache: see run.py and MP-README.md
exec python3 "$(dirname "$0")/run.py" "$@"
