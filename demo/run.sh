#!/bin/sh
# Demo of multi-parent sessions and the proof cache (see README.md in this directory).
#
# Usage: demo/run.sh [ISABELLE_TOOL]
#
# The Isabelle tool is the argument, else $ISABELLE_TOOL, else bin/isabelle of this
# repository. The parents must be built first (README.md). Runs four clean builds of the
# demo sessions (merge and baseline, each with and without the proof cache) plus a rebuild
# of the merge's child alone, and prints a table; logs are kept in a temporary directory.

LEFT="Jordan_Normal_Form"
RIGHT="HOL-Probability"
MERGE="$LEFT+$RIGHT"
THREADS="${THREADS:-8}"

DEMO="$(cd "$(dirname "$0")" && pwd)"
TOOL="${1:-${ISABELLE_TOOL:-$DEMO/../bin/isabelle}}"

# The Isabelle settings of the calling environment would redirect the tool to another
# installation (as in mp-tests/run.py): let it compute its own.
unset ISABELLE_HOME ISABELLE_SETTINGS_PRESENT ISABELLE_IDENTIFIER ISABELLE_HOME_USER \
  ISABELLE_TOOL

[ -x "$TOOL" ] || { echo "Isabelle tool not executable: $TOOL" >&2; exit 2; }
LOGS="$(mktemp -d "${TMPDIR:-/tmp}/mp-demo.XXXXXX")" || exit 2
echo "Isabelle tool: $TOOL"
echo "Logs: $LOGS"

# compile Isabelle/Scala now if its sources changed, so that no build below pays for it
"$TOOL" scala_build > "$LOGS/scala_build.log" 2>&1 ||
  { cat "$LOGS/scala_build.log"; exit 1; }

# build LOG ARGS...: one "isabelle build" in the demo directory, output to $LOGS/LOG
build() {
  log="$LOGS/$1"; shift
  echo "\$ isabelle build -d demo -v -o threads=$THREADS $*"
  if ! "$TOOL" build -d "$DEMO" -v -o threads="$THREADS" "$@" > "$log" 2>&1; then
    tail -n 30 "$log"
    echo "*** build failed, full log: $log" >&2
    exit 1
  fi
}

# seconds LOG: wall-clock of the whole command (its final "h:mm:ss elapsed time" line)
seconds() {
  sed -n 's/^\([0-9]*\):\([0-9]*\):\([0-9]*\) elapsed time.*/\1 \2 \3/p' "$1" | tail -n 1 |
    awk '{ print $1 * 3600 + $2 * 60 + $3 }'
}

# finished LOG SESSION: "elapsed / cpu" from "Finished SESSION (h:mm:ss elapsed time, ...)"
finished() {
  grep -F "Finished $2 (" "$1" | tail -n 1 |
    sed -n 's/.*(\([0-9:]*\) elapsed time, \([0-9:]*\) cpu time.*/\1 \/ \2/p'
}

# trusted LOG SESSION: "N/M" from "Proof cache SESSION: N/M theories trusted"
trusted() {
  grep -F "Proof cache $2: " "$1" | tail -n 1 | sed -n 's/.*: \([0-9]*\/[0-9]*\) theories trusted.*/\1/p'
}

# row LABEL LOG SESSION
row() {
  printf '| %s | %s s | `%s` %s | %s |\n' "$1" "$(seconds "$2")" "$3" \
    "$(finished "$2" "$3")" "$(trusted "$2" "$3")" >> "$LOGS/table.md"
}

# oracles DIR LOG: the oracles.out that Demo.thy writes (DIR = Merge or Base), kept as LOG
oracles() {
  cp "$DEMO/$1/oracles.out" "$LOGS/$2" && sed 's/^/    /' "$LOGS/$2"
}

rm -f "$DEMO/Merge/oracles.out"
build merge-cache.log -c "$MERGE" Demo_Merge
echo "  Oracles with the proof cache:"
oracles Merge merge-cache-oracles.txt
rm -f "$DEMO/Merge/oracles.out"
build merge-nocache.log -c -o proof_cache=false "$MERGE" Demo_Merge
echo "  Oracles without the proof cache:"
oracles Merge merge-nocache-oracles.txt
build base-cache.log -c Demo_Base
build base-nocache.log -c -o proof_cache=false Demo_Base
build child.log -c Demo_Merge

{
  echo '| build | wall-clock | re-loading session: elapsed / cpu | trusted |'
  echo '|---|---|---|---|'
} > "$LOGS/table.md"
row "merge, proof cache" "$LOGS/merge-cache.log" "$MERGE"
row "merge, \`proof_cache=false\`" "$LOGS/merge-nocache.log" "$MERGE"
row "baseline (\`sessions\`), proof cache" "$LOGS/base-cache.log" Demo_Base
row "baseline (\`sessions\`), \`proof_cache=false\` (stock)" "$LOGS/base-nocache.log" Demo_Base
row "child only, merge heap current" "$LOGS/child.log" Demo_Merge
echo
cat "$LOGS/table.md"
