#!/usr/bin/env bash
#
# install.sh -- install the Theories sidebar into an Isabelle2025-2 installation.
#
# Usage:
#   vscode-theories/install.sh [-n] ISABELLE_HOME
#
# Options:
#   -n   no extension: only install the sources and rebuild Isabelle/Scala
#        (skip "isabelle component_vscode_extension")
#
# Steps (each one idempotent, so the script can be re-run after every change):
#   1. back up every file of ISABELLE_HOME that is about to be overwritten
#      (first run only: FILE.orig is kept once it exists),
#   2. copy src/Tools/VSCode of this repository over the installation,
#   3. register src/Tools/VSCode/src/vscode_theories.scala in etc/build.props,
#   4. isabelle scala_build,
#   5. build the VSCode extension as component contrib/vscode_extension_theories
#      and register it in ISABELLE_HOME/etc/components, so that
#      ISABELLE_VSCODE_VSIX points at the new .vsix (needs network access:
#      component_vscode_extension downloads Node.js, yarn and vsce).
#
# WARNING: step 4 replaces lib/classes/isabelle.jar. Never run this against an
# installation whose Isabelle/Scala is in use by a running JVM (jEdit, VSCode,
# PIDE servers). A copy of an installation shares $ISABELLE_HOME_USER with the
# original unless its etc/ISABELLE_IDENTIFIER differs: give a development copy
# its own identifier, otherwise scala_build also rebuilds the user's own
# components against the copy's isabelle.jar.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_EXTENSION=true

usage() {
  echo "Usage: $0 [-n] ISABELLE_HOME" >&2
  exit 1
}

while getopts "n" opt; do
  case "$opt" in
    n) BUILD_EXTENSION=false ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))

[ "$#" -eq 1 ] || usage
ISABELLE_HOME="$(cd "$1" && pwd)"
ISABELLE="$ISABELLE_HOME/bin/isabelle"

if [ ! -x "$ISABELLE" ]; then
  echo "Error: '$ISABELLE' not found: not an Isabelle installation." >&2
  exit 1
fi

BUILD_PROPS="$ISABELLE_HOME/etc/build.props"
COMPONENTS="$ISABELLE_HOME/etc/components"
SOURCE_DIR="$REPO_DIR/src/Tools/VSCode"
TARGET_DIR="$ISABELLE_HOME/src/Tools/VSCode"
EXTENSION_NAME="vscode_extension_theories"
EXTENSION_DIR="$ISABELLE_HOME/contrib/$EXTENSION_NAME"
NEW_SOURCE="src/Tools/VSCode/src/vscode_theories.scala"
ANCHOR_SOURCE="src/Tools/VSCode/src/vscode_spell_checker.scala"

backup() {
  local file="$1"
  if [ -f "$file" ] && [ ! -e "$file.orig" ]; then
    cp -p "$file" "$file.orig"
    echo "  backup: ${file#"$ISABELLE_HOME"/}.orig"
  fi
}

echo "=== Installing the Theories sidebar into $ISABELLE_HOME ==="


echo
echo "Step 1/5: backing up files that will be overwritten ..."
(cd "$SOURCE_DIR" && find . -type f ! -name '*.orig' -print) | while read -r rel; do
  target="$TARGET_DIR/${rel#./}"
  if [ -f "$target" ] && ! cmp -s "$SOURCE_DIR/${rel#./}" "$target"; then
    backup "$target"
  fi
done
grep -qF "$NEW_SOURCE" "$BUILD_PROPS" || backup "$BUILD_PROPS"
if $BUILD_EXTENSION && ! grep -qxF "contrib/$EXTENSION_NAME" "$COMPONENTS"; then
  backup "$COMPONENTS"
fi


echo
echo "Step 2/5: copying src/Tools/VSCode ..."
rsync -rlt --checksum --itemize-changes \
  --exclude 'node_modules/' --exclude 'out/' --exclude '*.vsix' --exclude '*.orig' \
  "$SOURCE_DIR/" "$TARGET_DIR/" | sed -n 's/^>f[^ ]* /  /p'


echo
echo "Step 3/5: registering $NEW_SOURCE in etc/build.props ..."
if grep -qF "  $NEW_SOURCE \\" "$BUILD_PROPS"; then
  echo "  already present"
else
  if ! grep -qF "  $ANCHOR_SOURCE \\" "$BUILD_PROPS"; then
    echo "Error: anchor $ANCHOR_SOURCE not found in $BUILD_PROPS" >&2
    exit 1
  fi
  sed -i "\\|^  $ANCHOR_SOURCE \\\\\$|a\\  $NEW_SOURCE \\\\" "$BUILD_PROPS"
  grep -qF "  $NEW_SOURCE \\" "$BUILD_PROPS" || {
    echo "Error: failed to insert $NEW_SOURCE into $BUILD_PROPS" >&2; exit 1; }
  echo "  added after $ANCHOR_SOURCE"
fi


echo
echo "Step 4/5: isabelle scala_build ..."
"$ISABELLE" scala_build


if $BUILD_EXTENSION; then
  echo
  echo "Step 5/5: building the VSCode extension component ..."
  BUILD_TMP="$(mktemp -d)"
  trap 'rm -rf "$BUILD_TMP"' EXIT
  # component_vscode_extension is an admin tool (Admin_Tools service), which a
  # release only offers with the Admin component of the repository: provide the
  # service declaration via a minimal jar on the CLASSPATH instead.
  mkdir -p "$BUILD_TMP/admin/META-INF/isabelle"
  echo "isabelle.Admin_Tools" > "$BUILD_TMP/admin/META-INF/isabelle/services"
  "$ISABELLE" env sh -c '"$ISABELLE_JDK_HOME/bin/jar" cf "$1" -C "$2" META-INF' \
    sh "$BUILD_TMP/admin_tools.jar" "$BUILD_TMP/admin"
  mkdir "$BUILD_TMP/component"
  CLASSPATH="$BUILD_TMP/admin_tools.jar" \
    "$ISABELLE" component_vscode_extension -D "$BUILD_TMP/component"
  built=("$BUILD_TMP"/component/vscode_extension-*)
  if [ "${#built[@]}" -ne 1 ] || [ ! -d "${built[0]}" ]; then
    echo "Error: no component directory produced in $BUILD_TMP" >&2
    exit 1
  fi
  rm -rf "$EXTENSION_DIR"
  mv "${built[0]}" "$EXTENSION_DIR"
  echo "  component: contrib/$EXTENSION_NAME (built as ${built[0]##*/})"

  if grep -qxF "contrib/$EXTENSION_NAME" "$COMPONENTS"; then
    echo "  already registered in etc/components"
  else
    echo "contrib/$EXTENSION_NAME" >> "$COMPONENTS"
    echo "  registered in etc/components"
  fi

  vsix="$("$ISABELLE" getenv -b ISABELLE_VSCODE_VSIX)"
  echo "  ISABELLE_VSCODE_VSIX=$vsix"
  case "$vsix" in
    "$EXTENSION_DIR"/*.vsix)
      [ -f "$vsix" ] || { echo "Error: $vsix does not exist" >&2; exit 1; } ;;
    *)
      echo "Error: ISABELLE_VSCODE_VSIX does not point into $EXTENSION_DIR" >&2
      exit 1 ;;
  esac
else
  echo
  echo "Step 5/5: skipped (-n)"
fi

echo
echo "=== Done. Run \"isabelle vscode\" of this installation to (re)install the extension. ==="
