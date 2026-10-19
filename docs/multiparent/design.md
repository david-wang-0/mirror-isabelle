# Multi-parent sessions: design

Syntax (ROOT): `session D = B + C + E + theories …`, with any number of parents.

## Merge sessions

Poly/ML heaps have a single parent, so the heap chain stays linear:
`Sessions.Structure.make` synthesizes *merge sessions* and makes the last one D's real
parent. `"B+C"` has parent B, `sessions C`, and re-loads every theory of C's chain that is
not in B's chain (the `theories` groups of those sessions, names fully qualified, each
group with its original options plus `document=false`). Proofs of the re-loaded theories
are skipped through the [proof cache](proof-cache.md); a theory that was never checked
with real proofs is checked in full. For more parents fold left: `"B+C+E"` has parent
`"B+C"`.

C itself is a build prerequisite of `"B+C"` (`Info.build_prereqs`): it is built and must
be OK first (a failed C cancels the merge and D), its output shasum feeds the merge's input
shasum, but its heap is not loaded, and not stored for the merge either
(`Sessions_Multiparent.store_heap`, hook in `Build_Process`: stock `store_heap` counts
every ancestor, so `build C` without `-b` followed by `build D` would rebuild C just to
store a heap nobody loads).

Merge sessions are shared by name (`D2 = B + C` reuses `"B+C"`). Shortcuts compare heap
content (the non-merge sessions a chain covers, through other parents and merges): if C's
content is contained in B's, there is no merge (parent B); if B's is contained in C's, the
parent is C (e.g. `G = D + B` and `H = B + D` with `D = B + C` both get parent D). Only the
right parent's chain is re-loaded, so list the biggest parent first (`HOL + P` re-loads P;
`P + HOL` re-loads all of HOL, which works but took 122 s). A merge name that is already
a real session name (the AFP has `CoreC++`) is an error; cycles through other parents are
reported as cyclic session dependencies.

Theories keep their qualifier (`D` imports `C.Y`); theorems re-loaded by a merge carry the
`cached_proof` oracle (C's real proofs were checked when C was built).

## Session graphs and implementation

Scala only, in `src/Pure/Build`: the merge synthesis is `Sessions_Multiparent.make_infos`
(new file `sessions_multiparent.scala`), called from `Sessions.Structure.make`; the hooks
in original files are marked `// MP:`.

- Grammar `rep(session_name ~! "+")`; `Session_Entry/Info.other_parents` (an extra
  meta-info shasum entry only when non-empty, so ordinary sessions keep their digest);
  `Info.build_prereqs`.
- `Structure.heap_graph` (parent edges only) next to `build_graph` (parent and
  `build_prereqs` edges). `Store.session_heaps` uses `heap_requirements` (the linear
  chain); `Build_Process.Sessions.init` uses `build_graph.imm_preds` as dependencies.
- Merge sessions appear in `isabelle sessions`, `isabelle build -n -v` and `-l`; they are
  excluded from `session_directories`.

## Behaviour of the usual entry points

- `-l D` loads the chain (checked with `isabelle process_theories -l` on a test merge); the
  Isabelle/jEdit and Isabelle/VSCode `-R D` path
  (`Sessions.Background.load(session_requirements = true)`) yields the merge as logic
  (checked from Scala, not in the GUI).
- `build -R D` builds B, C and `"B+C"`; `-x C` excludes the merge and D; `-c C` cleans
  every merge and session above C (careful: `build -n -c` cleans too, as in stock Isabelle).

## Limits

Merge sessions show up as ordinary sessions (logic choosers; `-g` via the chapter groups
of the left parent). The merge re-runs everything except proofs (definitions, datatypes,
code setup, ML), so the saving is proportional to proof time. Theorems through a merge
depend on the `cached_proof` oracle. Schematic goals and `record_proofs` cannot skip;
neither can theories that were never certified by the proof cache (they are checked in
full), nor any theory with `-o proof_cache=false`.

## Soundness

A merge skips exactly the proofs of the theories the proof cache trusts: a re-loaded
theory whose content was not checked with real proofs before is checked in full. A merge
is built only after C was built OK (C's sources are in the merge's sources shasum, C's
output shasum in its input shasum), so normally all of C's theories are certified.

An earlier version gave merges a blanket `skip_proofs=true` and relied on C's build being
current with the same options; but without `build_thorough` a change of content options
such as `skip_proofs` does not make a heap outdated, so that argument had a gap, which the
per-theory keys close. Every skipped theorem carries the `cached_proof` oracle, so nothing
is trusted silently at the kernel level. The argument for the cache itself is in
[proof-cache.md](proof-cache.md#soundness).
