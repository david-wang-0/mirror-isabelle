# Heap-merge spike: sibling heaps in one process via Poly/ML modules

Spike of 2026-10-19 on branch `spike/heap-merge` (from `proof-cache` dfa52bd). Question:
can one Isabelle process hold the theories of two **sibling** session heaps (`SB = Pure + …`,
`SC = Pure + …`) without re-loading SC's theories, i.e. true multi-parent heaps, by
exporting SC's theory values as a Poly/ML *module* (`PolyML.SaveState.saveModule`) and
loading it into a process on SB's heap? Saved states themselves are a linear chain (one
parent, children overwrite their ancestors' mutable segments), so siblings can never be
co-loaded as saved states; this was not re-tested.

## Verdict

**Feasible only with a newer Poly/ML plus substantial Isabelle-side work; not feasible with
the Poly/ML 5.9.2 that Isabelle2025-2 (and Isabelle2026, still on the `fixes-5.9.2`
commit ccd3e3717f72) ships.**

- **Poly/ML 5.9.2: no.** `saveModule` aborts on an assertion in any process with a loaded
  saved state (E1). With the assertion binary-patched out, a module copies everything it
  reaches, i.e. all of Pure (33.8 MB for an 11 KB theory, 64-bit; 236 MB for `Main`), and
  in Isabelle's default `x86_64_32` platform loading any module crashes (E1, E2, E4). On
  x86_64 the loaded copy is useless: its ML types differ (`?.Basic_Context.theory`) and
  every theory-data access raises `Match` (E2).
- **Poly/ML master (4221cec, 2026-10-10, unreleased): the Poly/ML side works.**
  `saveDependentModule` with the Pure saved state as a dependency writes a 62 KB module of
  `SC.Y`, which loads into a process on Pure + SB, shares Pure (`pointer_eq` true), type
  checks without casts and reads its theory data (E5). Master also builds and runs
  Isabelle2025-2's Pure unchanged.
- **Isabelle side: needs real work.** Sibling sessions allocate theory ids, data kinds and
  `serial`s from counters that both start from the same Pure state, so they collide: X and
  Y get the same theory id, `Theory.begin_theory "Z" [X, Y]` silently drops a parent, and
  the kernel accepts `Conjunction.intr lx ly` as a theorem of `SB.X` mentioning the
  undeclared `Y.b` (E3, E5). With the counters made distinct by hand the merge works for
  terms and theorems, but data kinds registered by the sibling (`Context.kinds`, a
  `Synchronized` var in Pure's heap) are not part of the module, so Y's own theory data are
  dropped from `Z = [X, Y]` and `Z' = [Y, X]` fails with `Fail "Invalid theory data
  identifier"` (E6).

## Setup

This tree (`bin/isabelle`, user directory `Isabelle2025-2-mp`), Poly/ML 5.9.2 (`contrib/
polyml-5.9.2-2`). Spike sessions in `tmp/spike` (gitignored; the sources are reproduced
below):

```
session SB in b = Pure + theories X      (* X: axiomatization a, lemma lx, Theory_Data Data_X *)
session SC in c = Pure + theories Y      (* Y: axiomatization b, lemma ly, Theory_Data Data_Y *)
session SD in d = SB + sessions SC theories Z   (* Z imports SB.X SC.Y *)
```

`X.thy`/`Y.thy` each declare `axiomatization a :: "prop" where ax_a: "PROP a"`, a lemma
`PROP a ⟹ PROP a` by assumption, and `structure Data_X = Theory_Data(...)` with a
`setup` that changes it (Y: `int list`, X: `string list`).

The ML experiments run in **raw `poly`** on the session heaps, because they need a patched
`poly` and Isabelle's tooling always takes `$POLYML_HOME/$ML_PLATFORM/poly`:

```sh
# run.sh POLY "Pure SC" file.ML...  (HD = heap directory of the platform)
export ISABELLE_PROCESS_OPTIONS=/tmp/spike/options.yxml    # from: isabelle options -x
exec "$POLY" -q --minheap 500 \
  --eval "(PolyML.SaveState.loadHierarchy [\"$HD/Pure\",\"$HD/SC\"]; PolyML.print_depth 0)" \
  --eval "Options.load_default ()" --use full_polyml.ML --use e1.ML \
  --eval 'OS.Process.exit OS.Process.success' < /dev/null
```

Isabelle hides `PolyML.SaveState` and `RunCall` after bootstrap (`ML_Bootstrap.thy` rebinds
a restricted `PolyML` in the global name space). The unrestricted structures are still in
the ML environment of theory `ML_Bootstrap`; `full_polyml.ML` re-exports them:

```sml
val _ =
  let
    val thy = Thy_Info.get_theory "ML_Bootstrap";
    val full = Context.setmp_generic_context (SOME (Context.Theory thy))
      (fn () => #lookupStruct ML_Env.name_space "PolyML") ();
  in #enterStruct ML_Name_Space.global ("PolyML_Full", Option.valOf full) end;
(* likewise RunCall -> RunCall_Full *)
```

(Inside a theory the same works with `imports … ML_Bootstrap` plus
`declare [[ML_read_global = true]]`, and `declare [[ML_write_global = true]]` in the
theory that defines the structures to be saved, because `saveModule` looks names up in
`PolyML.globalNameSpace` and `Pure.thy` ends with `ML_write_global = false`.)

## E0: baseline

```
$ isabelle build -d tmp/spike SB SC SD
Building SB ... Finished SB    Running SC ... Finished SC
Running SD ... Proof cache SD: 1/2 theories trusted ... Finished SD
```

SD (parent SB) re-loads `SC.Y` from source (here proof-cached). Heaps (x86_64_32): Pure
25,096,417 B, SB 602,794 B, SC 602,442 B.

## E1: write a module of a theory value (in a process on Pure + SC)

```sml
structure Spike_Y = struct
  val thy = Thy_Info.get_theory "SC.Y";
  val ly = Global_Theory.get_thm thy "Y.ly";
  val kinds = Context.data_kinds ();
end;
structure Spike_Ctl = struct val xs = [1, 2, 3] end;           (* control *)
structure Spike_Pure = struct val thy = Thy_Info.get_theory "Pure" end;
PolyML_Full.SaveState.saveModule ("/tmp/spike/Y.mod",
  {structs = ["Spike_Y"], functors = [], sigs = [], onStartup = NONE});
```

**Stock Poly/ML 5.9.2 (both `x86_64_32` and `x86_64`), even for the 3-element control:**

```
poly: exporter.cpp:767: void Exporter::RunExport(PolyObject*): Assertion `memEntry == tableEntries' failed.
... Aborted (core dumped)
```

`RunExport` sizes the segment table for *all* permanent spaces but fills it only with the
executable's (hierarchy 0) ones, so any process with a loaded saved state fails. This is
Poly/ML issue #278 ("saveModule assertion failure after loadState with multi-hierarchy
heap", closed; regression test on master 2026-05-02). For the spike the 6-byte `jne` to the
`__assert_fail` call was NOP-ed in copies of `poly` under `/tmp/spike/polyml/` (the
mismatch is harmless: the table is just over-allocated).

With the patched `poly`:

| platform | module | file size | `saveModule` time |
|---|---|---|---|
| x86_64_32 | `Spike_Ctl` | 2,596 B | 0.016 s |
| x86_64_32 | `Spike_Pure` (theory Pure) | 17,059,444 B | 0.090 s |
| x86_64_32 | `Spike_Y` (theory SC.Y + `ly`) | 17,062,412 B | 0.090 s |
| x86_64 | `Spike_Ctl` | 8,552 B | 0.018 s |
| x86_64 | `Spike_Pure` | 33,812,152 B | 0.109 s |
| x86_64 | `Spike_Y` | 33,823,496 B | 0.108 s |

The x86_64 Pure heap is 32,289,605 B and SC's 1,187,275 B. Y's own content is the
~11 KB difference to `Spike_Pure`; the rest is a copy of Pure: `CopyScan` leaves only
spaces with `hierarchy < 1` (the executable) in place, and a loaded saved state is
hierarchy ≥ 1. Diagnostics printed in SC: Y's `Data_Y` has data kind 192, theory ids
Y = 4718, Pure = 4313 (x86_64), `serial ()` = 56990.

## E2: load the module into a process on Pure + SB

**x86_64_32 (Isabelle's default platform): loading crashes.** Already in bare `poly`
(no Isabelle), `saveModule` of `structure S = struct val x = 1 end` then, in a second
process, `loadModuleBasic` returns 1 entry, and the first use of it
(`Universal.tagIs PolyML.SaveState.Tags.structureTag`) segfaults (exit 139). Same in a
Pure + SB process (where the stock `loadModule` also does not enter the structure).
The same bare test works on x86_64, so modules are broken in 32-in-64 mode in 5.9.2.
Everything below is x86_64 (`isabelle build -b -o ML_system_64 -d tmp/spike SB SC`,
Pure took 13 s).

```
SPIKE SB: theory_identifier X = 4718, Pure = 4313
SPIKE SB: data_kinds declared in X.thy: 192
SPIKE SB: serial now = 56990
SPIKE loadModule /tmp/spike/Y.mod: 0.020 s
```

Using the loaded structure as a theory fails at type checking:

```
val thy_Y : theory = Spike_Y.thy;
error: Pattern and expression have incompatible types.
   Pattern: thy_Y : Basic_Context.theory : theory
   Expression: Spike_Y.thy : ?.Basic_Context.theory
   Reason: Can't unify theory with ?.Basic_Context.theory (Different type constructors)
```

The module carries its own copy of Pure's type constructors. Forcing the types with
`RunCall_Full.unsafeCast` (same source, same layout):

```
SPIKE E2 theory_long_name Y = SC.Y
SPIKE E2 theory_identifier Y (module copy) = 4718
SPIKE E2 parents_of Y = Pure
SPIKE E2 eq_thy (Pure of Y, Pure) = true
SPIKE E2 pointer_eq (Pure of Y, Pure) = false
SPIKE E2 subthy (Pure, Y) = true
SPIKE E2 theory_long_name (theory_of_thm ly) = SC.Y
SPIKE E2 prop_of ly (raw term) = Term.$ (Term.$ (Term.Const ("Pure.imp", …)), Term.Const ("Y.b", …)), Term.Const ("Y.b", …))
SPIKE E2 Sign.const_type Y Y.b RAISES Match
SPIKE E2 Global_Theory.get_thm Y "Y.ly" RAISES Match
SPIKE E2 string_of_thm (init_global Y) ly RAISES Match
SPIKE E2 string_of_thm (init_global Pure) ly = ??.Y.b \<Longrightarrow> ??.Y.b
SPIKE E2 theory_data_sizeof1 Y (count) = 39
```

Plain data (names, ids, terms) survives; every theory-data access raises `Match`: the
`Theory_Data` functor projects with `fn Data x => x`, and the module's data are packets of
*copied* exception constructors. Identity checks compare integer ids, so they report the
copied Pure as equal to the real one.

## E3: siblings in one theory

```
SPIKE E3 eq_thy (X, Y) = true
SPIKE E3 subthy (X, Y) = true
SPIKE E3 Thm.transfer X ly = SC.Y
SPIKE E3 data kind 192 owner in this process = 192 (line 5 of "~~/tmp/spike/b/X.thy")
SPIKE E3 begin_theory Z [X, Y] = parents = SB.X; ancestors = SB.X, Pure
SPIKE E3 begin_theory Z [Y, X] RAISES Match
SPIKE E3 … combination of lx and ly RAISES Match
```

X and Y were the first theory created after Pure in their respective processes, so they
got the same id (`Context.new_id`, a counter in the Pure heap); `make_parents` removes
duplicates by `eq_thy`, so Y vanishes from Z without an error. `Data_X` and `Data_Y` both
got data kind 192 (`Context.data_kind = Counter.make ()`); in the SB process kind 192 is
registered to `Data_X`, so a merged theory would apply X's merge to Y's data. The `serial`
counter (name-space entry ids, among others) was at the same value 56990 in both, so
sibling entries collide as well. There is no Thy_Info API to register a finished theory
(`change_thys` is local), so `theory Z imports SB.X SC.Y` was tested through
`Theory.begin_theory`, which is what the import does after resolving names.

## E4: cost of the copy, and what a fix needs

`Main` of HOL (x86_64_32, patched `poly`, process on Pure + HOL): 236,222,744 B in
1.05 s; the HOL heap is 218,192,614 B and Pure 25,096,417 B, i.e. the module is the whole
chain. So with 5.9.2 a "module of the right parent" is never cheaper than its heaps, and
it is not even usable.

## E5: the same with Poly/ML master

Poly/ML master (git 4221cec of 2026-10-10; module dependencies, "Add the ability to
include a saved state as a dependency of a module", 2026-06-04) was built in
`/tmp/spike/polyml-master` (`./configure --disable-shared --enable-intinf-as-int
--without-gmp`, x86_64 only). Isabelle was pointed at it without touching this tree's user
directory: `USER_HOME=/tmp/spike/home isabelle build -b -o ML_system_64 -d tmp/spike
SB SC` with `POLYML_HOME=/tmp/spike/polyml-master` in
`/tmp/spike/home/.isabelle/Isabelle2025-2-mp/etc/settings`. Pure built in 13 s, as with
5.9.2.

In a process on Pure + SC:

```sml
val hier = PolyML_Full.SaveState.showHierarchyWithIds ();   (* [(id, Pure), (id, SC)] *)
PolyML_Full.SaveState.saveDependentModule ("/tmp/spike/Ym.mod",
  {structs = ["Spike_Y"], functors = [], sigs = [], onStartup = NONE}, [hd hier]);
```

```
SPIKE hierarchy id 3CE28811AE218F0C …/Pure
SPIKE hierarchy id B4AAD8A10AFE6728 …/SC
SPIKE saveDependentModule Spike_Y -> /tmp/spike/Ym.mod deps=1: 0.029 s, id 4EF210AD409B9573
SPIKE saveDependentModule Spike_Pure -> /tmp/spike/Pm.mod deps=1: 0.027 s
SPIKE saveDependentModule Spike_Ctl -> /tmp/spike/Ctlm.mod deps=1: 0.021 s
```

Sizes: `Ym.mod` 62,014 B, `Pm.mod` 4,310 B, `Ctlm.mod` 8,782 B. (A plain `saveModule`
without dependencies of `Spike_Y`, run after two other saves in the same process, aborted
with `exporter.cpp:1033: unsigned int Exporter::findArea(void*): Assertion '0' failed.`;
not pursued.)

In a process on Pure + SB, after `loadModule "/tmp/spike/Ym.mod"` (0.000 s), the E2/E3
script with plain `val thy_Y : theory = Spike_Y.thy` (no cast needed):

```
SPIKE E2 eq_thy (Pure of Y, Pure) = true
SPIKE E2 pointer_eq (Pure of Y, Pure) = true
SPIKE E2 Sign.const_type Y Y.b = Term.Type ("prop", [])
SPIKE E2 Global_Theory.get_thm Y "Y.ly" = b \<Longrightarrow> b
SPIKE E2 string_of_thm (init_global Y) ly = b \<Longrightarrow> b
SPIKE E3 eq_thy (X, Y) = true
SPIKE E3 subthy (X, Y) = true
SPIKE E3 Thm.transfer X ly = SC.Y
SPIKE E3 begin_theory Z [X, Y] = parents = SB.X; ancestors = SB.X, Pure
SPIKE E3 begin_theory Z [Y, X] = parents = SC.Y
SPIKE E3 Conjunction.intr lx ly (theory of result) = SB.X: (a \<Longrightarrow> a) &&& (??.Y.b \<Longrightarrow> ??.Y.b)
```

The Poly/ML problems are gone; what is left is the id collision of E3, now with an unsound
result: a theorem certified for `SB.X` that mentions a constant X does not have.

## E6: siblings with distinct counters (Poly/ML master)

To see what remains once ids are unique, `SC2 = Pure + theories Pad Y` was built, where
`Pad` (imports Pure) declares one `Theory_Data` and calls `serial ()` twice, so `SC2.Y`
gets other numbers (theory id 4842 vs X's 4716; `Data_Y` kind 194 vs X's 192). Module
`Y2m.mod` (62,302 B) loaded into Pure + SB:

```
SPIKE F theory ids X, Y(SC2) = 4716, 4842
SPIKE F data_kinds of Y (from its own snapshot) = 192 (line 3 of "~~/tmp/spike/c2/Pad.thy"), 194 (line 5 of "~~/tmp/spike/c2/Y.thy")
SPIKE F data_kinds registered in this process (.thy) = 192 (line 5 of "~~/tmp/spike/b/X.thy")
SPIKE F eq_thy (X, Y) = false
SPIKE F Conjunction.intr lx ly RAISES ERROR "Cannot join unrelated theory certificates X and Y"
SPIKE F Z parents = SB.X, SC2.Y
SPIKE F Z: Y.ly = b \<Longrightarrow> b
SPIKE F Z: X.lx = a \<Longrightarrow> a
SPIKE F Z: Conjunction.intr (transfer lx) (transfer ly) = (a \<Longrightarrow> a) &&& (b \<Longrightarrow> b)
SPIKE F theory_data_sizeof1 Y (all kinds) RAISES Fail "Invalid theory data identifier"
SPIKE F theory_data_sizeof1 Z (all kinds) = 39
SPIKE F theory_data_sizeof1 X (all kinds) = 39
SPIKE F Z' = [Y, X]: theory_data_sizeof1 (all kinds) RAISES Fail "Invalid theory data identifier"
```

With unique ids the kernel behaves (unrelated certificates are refused, the merged `Z`
has both parents, transfers both lemmas and combines them). But kind 194 was registered
in SC2's process by mutating `Context.kinds`, a `Synchronized` var that lives in Pure's
saved state; the module references that var without its SC2-era contents. `merge_data`
folds over the *registered* kinds, so `Z = [X, Y]` silently loses `Data_Y`, and a theory
whose first parent is Y carries an unregistered kind.

## What a fix needs

Poly/ML:

- Module dependencies on saved-state levels (done on master, unreleased; Isabelle2026
  still uses `fixes-5.9.2` ccd3e3717f72). Isabelle would have to move to a Poly/ML with it
  (a new `polyml` component; master built Isabelle2025-2's Pure unchanged here). Small
  for us, but outside our control and timing.
- `x86_64_32` (Isabelle's default): 5.9.2 crashes on any loaded module; master's 32-in-64
  build was not tested. Unknown; fallback is `ML_system_64` (larger heaps: Pure 32 MB instead of 25 MB).
- Module dependencies are content hashes of the saved-state files, so a module of C works
  only on top of byte-identical ancestor heaps (the common prefix of B's and C's chains).
  Fine for heaps from one build; no effort.

Isabelle (each item is a change to `src/Pure`, not a hook):

- **Globally unique identities across sessions** (theory ids `Context.new_id`, data kinds
  `Context.data_kind`, Proof_Data kinds, `serial ()` used by name-space entries, proof
  terms and much else; any other `Counter.make` in Pure). E.g. a per-session offset
  derived from the session (a block of the id space per session, recorded in the heap),
  set before the session's first theory. Medium (find every counter; Bitset-based theory
  ids need block numbers, not offsets); about 1-2 weeks including review of every
  counter's uses.
- **Registry deltas as part of the export.** Everything a session adds to mutable state in
  its ancestors' heaps: `Context.kinds` for Theory_Data and Proof_Data (with their `empty`
  and `merge` closures), `Thy_Info.thys` entries (with `deps` and presentation segments),
  the global ML name space (structures written with `ML_write_global`), and any other
  `Synchronized`/`Unsynchronized` registry in Pure (session resources, options, keywords
  if global). The export root of a session would be a record of these deltas, saved as a
  module depending on the common ancestor, and an import function would replay them into
  a process with conflict checks. Large: about 2-4 weeks to enumerate and test; the risk
  is a missed registry, which fails silently (as `Data_Y` did here).
- **Build integration**: for `D = B + C` with common ancestor A, build C as usual, export
  C's module relative to A, then the merge session `"B+C"` loads B's chain, loads C's
  module, replays it and saves the merge heap with `saveChild` (a saved state copies module
  data into itself, so later loads need no module). Replaces the re-loading of C's
  theories in `Sessions_Multiparent`. Medium, 1 week, once the two items above exist.
- A finished-theory registration API in `Thy_Info` (none today; `change_thys` is local).
  Small.

## Remaining measurement

`Main` (HOL) was only measured with 5.9.2 (no dependencies). With master the module of a
HOL-based sibling would contain only that sibling's own heap level (expected roughly the
size of its saved-state file); not measured, as it would have needed a 64-bit HOL build
on master.

## Recommended next step

Do not start the implementation now. The Poly/ML half depends on an unreleased Poly/ML
that Isabelle does not use yet, and the Isabelle half (unique ids, registry export and
replay) is several weeks of changes deep in `src/Pure` whose failures are silent. The
proof-cache re-load of the right parent stays the practical route. Revisit when a Poly/ML
release with module dependencies is out and Isabelle adopts it; at that point the first
step is a one-day prototype of the identity part (per-session id blocks) plus replay of
`Context.kinds` and `Thy_Info.thys` only, measured on a HOL-based pair (this spike's E6
setup with `HOL` as common ancestor).

Spike artefacts: the sessions and ML scripts in `tmp/spike` (`ROOT`, `b/`, `c/`, `c2/`,
`d/`, `e1/`, `raw/*.ML`, `raw/run.sh`) are committed only on the unpublished branch
`spike/heap-merge`; logs, modules and the patched and master `poly` binaries were left in
`/tmp/spike` and are not kept.
