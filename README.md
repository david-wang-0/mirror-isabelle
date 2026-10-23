# Isabelle2025-2 with a Theories sidebar for Isabelle/VSCode

A fork of the [Isabelle2025-2](https://isabelle.in.tum.de) release (on the official GitHub
mirror) that gives Isabelle/VSCode the equivalent of Isabelle/jEdit's *Theories* panel:
a *Theories* view in the activity bar listing every theory of the prover session in
dependency order, with its processing status (unprocessed / running / warned / failed),
a "required" checkbox per theory, a *Purge Theories* button, and click-to-open.

The change is confined to `src/Tools/VSCode` (one new Scala file, one new tree view in the
extension) plus one line in `etc/build.props`.

## Trying it

From a checkout of this branch, install into an unpacked Isabelle2025-2 release:

```sh
vscode-theories/install.sh ISABELLE_HOME
ISABELLE_HOME/bin/isabelle vscode
```

The script rebuilds Isabelle/Scala, so do not run it against an installation that a
running jEdit, VSCode or PIDE server uses. Building the extension downloads Node.js, yarn
and vsce.

Details (design, protocol, required/purge semantics, development loop, test):
[docs/vscode-theories/README.md](docs/vscode-theories/README.md). The original README of
the release is [README](README).
