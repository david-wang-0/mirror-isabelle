#!/bin/sh
# Test suite for multi-parent sessions and the proof cache: see run.py and docs/multiparent/testing.md
exec python3 "$(dirname "$0")/run.py" "$@"
