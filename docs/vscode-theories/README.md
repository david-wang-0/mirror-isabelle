# Theories sidebar for Isabelle/VSCode

Isabelle/jEdit has a *Theories* panel: every theory of the running prover session with
its processing status (unprocessed / running / warned / failed), a "required" checkbox,
and a *Purge* button. Isabelle/VSCode has had nothing comparable (it has been on the
wish list since the first Isabelle/VSCode report in 2017). This branch adds it to the
**Isabelle2025-2** release.

## Layout

Branch `isabelle2025-2-vscode-theories` of this mirror, based on the Isabelle2025-2 release
commit (`8d9ad3f298`) and independent of the other feature branches.
`git diff 8d9ad3f298 -- src etc` is the patch itself; the
helpers live in `vscode-theories/` (`install.sh`, `lsp_smoke.py`) and this document in
`docs/vscode-theories/`.

## Design

The server side follows jEdit's `Theories_Dockable` / `Theories_Status`
(`src/Tools/jEdit/src/theories_{dockable,status}.scala`). `VSCode_Theories`
(`src/Tools/VSCode/src/vscode_theories.scala`) keeps a `Document_Status.Nodes_Status`,
updates it on `Session.Commands_Changed` and `Session.Phase`, and pushes a
`PIDE/theories_status` notification built from `Document_Status.Node_Status.json`. Output
is coalesced with `Delay.first(vscode_output_delay)` (not `Delay.last`: while the prover
works, commands change more often than the delay, so a trailing delay would hold the
status back until the prover is idle) and sent only when it differs from the last one,
or on an explicit request. The wiring copies the Sledgehammer panel
(`vscode_sledgehammer.scala`, `lsp.scala`, `language_server.scala`).

The client side is a native VSCode tree view (not a webview) in its own activity-bar
container *Theories*, in the style of upstream's `documentation_treeview.ts` (Isabelle
development version, after 2025-2): `extension/src/theories_treeview.ts`. Each theory is
one item: status icon (passed / failed / spinning while running / empty circle while
pending), a short description (percentage, error or warning count, or a check mark), a
Markdown tooltip with the counts, a "required" checkbox, and click-to-open. The view's
description shows the prover phase ("Prover: ready"). The title bar has *Purge
Theories* (`isabelle.theories-purge`).

### Protocol

| Message | Direction | Parameters |
|---|---|---|
| `PIDE/theories_request` | client → server | none; answered by a full `PIDE/theories_status` |
| `PIDE/theories_status` | server → client | `{phase, theories}` |
| `PIDE/theories_set_required` | client → server | `{uri, required}` |
| `PIDE/theories_purge` | client → server | none |

`phase` is `Session.Phase.print` (`startup`, `ready`, `shutdown`, ...). `theories` lists
the theories in `topological_order` of the current document version, filtered as in jEdit
(non-empty, not suppressed, at least one command). Each entry is `Node_Status.json`
(`ok`, `total`, `unprocessed`, `running`, `warned`, `failed`, `finished`, `canceled`,
`consolidated`, `percentage`) plus `name` (theory name, e.g. `Draft.A`), `base_name`,
`uri` (the file, encoded like the other LSP messages), `overall` (`ok` / `failed` /
`pending`, loaded theories counting as `ok` as in jEdit) and `required`.

### Required and Purge

Isabelle/VSCode already had the jEdit default: `VSCode_Model.init` marks a model as
required only if its file format produces a theory (`File_Format.registry.is_theory`);
ordinary theories are not required and get checked because they are visible (caret
perspective) or imported. This patch keeps that default; the checkbox only lets the user
change it per theory. `PIDE/theories_set_required` sets `node_required` of the model
(`VSCode_Resources.set_node_required`, after jEdit's `Document_Model.node_required`) and
flushes the new perspective.

`PIDE/theories_purge` follows jEdit's `Document_Model.flush_edits(purge = true)` and
`File_Model.purge_edits`, in `VSCode_Resources.flush_input(purge = true)`. A theory model
is removed when

- it is closed in the editor (`external_file`: loaded as a dependency or closed by the
  client),
- it is not required,
- it has no pending text edits (before this flush) and an empty perspective,
- and it is not among `resources.dependencies(...)` of the theories that stay: the open
  ones and those that cannot be purged by the rules above.

The removal edits go to the prover together with the regular edits, the models are
dropped from the state (so a later `resolve_dependencies` only reloads what is still
imported), their diagnostics are cleared on the client, and the file watcher forgets
directories no remaining model lives in. Auxiliary files (non-theory models) are never
purged.

## Installing

```sh
vscode-theories/install.sh [-n] ISABELLE_HOME
```

It installs into an unpacked release (or a copy of one) from a checkout of this branch.
`etc/build.props` is not copied but patched, because installations may carry other local
lines in it.

1. backs up every file of the installation it is about to overwrite, once, as `FILE.orig`;
2. copies `src/Tools/VSCode` into the installation;
3. adds `src/Tools/VSCode/src/vscode_theories.scala` to `etc/build.props` (after
   `vscode_spell_checker.scala`; idempotent, other local lines are kept);
4. runs `isabelle scala_build`;
5. unless `-n`: builds the extension with `isabelle component_vscode_extension` (downloads
   Node.js, yarn and vsce, so it needs network access) as component
   `contrib/vscode_extension_theories`, registers it in the installation's own
   `etc/components` (not the user's), and checks that `isabelle getenv
   ISABELLE_VSCODE_VSIX` now points at the new `.vsix`. `component_vscode_extension` is an
   admin tool, which a release only offers together with the repository's `Admin`
   component; the script provides the `Admin_Tools` service declaration through a minimal
   jar on the `CLASSPATH` instead. The release's own `contrib/vscode_extension-*` stays as
   it is.

Then `isabelle vscode` of that installation reinstalls the extension, because its checksum
changed. Every step is idempotent, so re-run the script after each change.

## Development loop

Never rebuild the Isabelle installation that running prover sessions use: `isabelle
scala_build` replaces `lib/classes/isabelle.jar` under any live JVM (jEdit, VSCode,
PIDE servers), which can crash those JVMs. Develop against a **separate copy** of
the installation and only install into the real one when no Isabelle JVM is running.

A copy has the same `etc/ISABELLE_IDENTIFIER` and hence the same `$ISABELLE_HOME_USER`
as the original. Its `scala_build` would then also rebuild the user's own Scala
components (registered in `$ISABELLE_HOME_USER/etc/components`) against the copy's
`isabelle.jar`, under the original's running JVMs, and `isabelle vscode` of both would
share one VSCodium profile. So give the copy its own identifier, and run it with the
outer installation's settings variables removed from the environment:

```sh
cp -a $ISABELLE_HOME $COPY
printf '%s' Isabelle2025-2-dev > $COPY/etc/ISABELLE_IDENTIFIER
env -u ISABELLE_HOME vscode-theories/install.sh $COPY
python3 vscode-theories/lsp_smoke.py $COPY
```

The copy then needs heaps of its own: build them, or copy `Pure` and `HOL` (with their
`log/*.db` files) into `$COPY/heaps/`.

## Test

`vscode-theories/lsp_smoke.py ISABELLE_HOME` (options: `-l LOGIC`, default `HOL`; `-L LOGFILE` for
the server log; `-t SECONDS` per step; `--phase1`) starts `isabelle vscode_server`, speaks
LSP over stdio and opens three generated theories `A` ← `B` ← `C` in a temporary
directory, `B` with a failing `lemma "False" by simp`, the caret in `C`. It checks that

- `PIDE/theories_status` lists `A`, `B`, `C` in topological order with all fields, `A`
  ends `ok`, `B` ends `failed`, the phase is `ready`, and `PIDE/theories_request` forces a
  status message;
- nothing is required by default and `PIDE/theories_set_required` flips `required`;
- `PIDE/theories_purge` keeps `C` while it is open, and after `didClose` while it is
  required; once `C` is not required it disappears and its diagnostics are cleared, while
  `B` (open) and `A` (closed, imported by `B`) stay;
- the server shuts down cleanly.

The GUI itself is not covered: after `isabelle vscode`, look at the *Theories* activity
bar entry (icon, item status icons and colours, descriptions, tooltips, the checkbox,
click-to-open, the *Purge Theories* title button, and "Prover: ..." in the view header).

## Upstream

After the Isabelle2026 release, port it to the Isabelle development repository (where
Isabelle/VSCode has become *Isacode* on a newer VSCodium) and offer it on the isabelle-dev
mailing list.
