# Testing

## Running the suite

```
mp-tests/run.sh [-l] [--slow] [--isabelle TOOL] [CASE ...]
```

`mp-tests/run.sh` (Python 3, standard library only) copies `mp-tests/src` (ROOT and
theories of the `MPT_*` sessions) to `mp-tests/work` (git-ignored), and
`mp-tests/afp-demo` to `mp-tests/work/afp-demo`, with a fresh nonce in the theories that
must be new to the proof cache (a token `ML ‹val nonce = "…"›`: normalised keys ignore
comments), then runs the cases (all default cases, or those named;
`--slow` adds the slow ones; `-l` lists them) with
`isabelle build -d mp-tests/work -v -o threads=8` on the normal user heaps of that Isabelle.

The Isabelle tool is `--isabelle TOOL`, else `$ISABELLE_TOOL`, else `bin/isabelle` of this
repository; the suite prints which one it uses, with its `ISABELLE_HOME` and
`ISABELLE_HOME_USER`. It removes the Isabelle settings variables of the calling
environment (`ISABELLE_HOME`, `ISABELLE_SETTINGS_PRESENT`, `ISABELLE_IDENTIFIER`,
`ISABELLE_HOME_USER`, `ISABELLE_TOOL`) before calling the tool, so that a shell which
exports another installation's `ISABELLE_HOME` does not redirect it. Do the same when
calling this Isabelle by hand from such a shell:

```
env -u ISABELLE_HOME -u ISABELLE_SETTINGS_PRESENT -u ISABELLE_IDENTIFIER \
  -u ISABELLE_HOME_USER bin/isabelle build …
```

HOL must be built (case `hol_uptodate` checks that `build -n -v HOL` has nothing to do).
Every assertion prints a `PASS` or `FAIL` line; the exit code is 1 if any failed. Default
cases: about 6.7 minutes (173 assertions on 2026-10-19, all passed); `--slow` adds about 7
minutes (both slow cases passed on 2026-10-19).

Do not run two suites, or a suite and other builds of the same Isabelle, at the same
time: case `robustness` temporarily removes and replaces `proof_cache.db` (restored from a
backup).

## Cases

- `hol_uptodate` (also with `-o proof_cache=false`: not a content option)
- `plain_sessions` (`sessions` import trusts Y, timing, oracles, `proof_cache=false` =
  stock)
- `merge` (build order, trusted merge, timing, oracles: `cached_proof` exactly on facts
  re-loaded or depending on re-loaded ones, none on facts of the heap chain, merge reuse
  by `MPT_D2`)
- `parent_failure` (failing parent cancels merge and child, no cache writes)
- `three_parents`
- `diamond` (`MPT_D + MPT_F` over shared B, C; shortcut `MPT_D + MPT_B`)
- `edit_miss` (edited theory misses, is re-certified, dependants trust it again; a parent
  built without heap is not rebuilt for the merge)
- `no_write` (no rows under `skip_proofs`, `quick_and_dirty`; a trusted theory is not
  re-certified)
- `proof_cache_false_merge`
- `parallel` (`MPT_PAR`: an untrusted theory loaded in parallel with the trusted
  `MPT_C.Y`, and an untrusted child of Y in the same session, carry no `cached_proof`: the
  flag does not leak)
- `loaded_files` (editing only an `ML_file` or an `external_file` misses exactly that
  theory; reverting hits the old key)
- `import_change` (an edited import in the same session, and an edited theory of the
  parent heap, make the unchanged importer miss; reverting the parent restores all hits)
- `options` (a changed content option, `ML_print_depth`, misses and certifies a new key; a
  non-content option, `timeout_scale`, hits)
- `skip_oracle` (`sorry` under a theory-local `quick_and_dirty` is never certified and
  keeps `skip_proof` in a cached load; a theory using `Skip_Proof.make_thm` like a tool is
  certified, the stored fact keeps `skip_proof`, a lemma proved from it shows only
  `cached_proof` when cached, the documented limit)
- `robustness` (no database: re-created; database path unusable or read-only: warnings,
  build OK; two `isabelle build` processes writing concurrently, three rounds: before the
  busy retry, one of the two writes was lost in one of five runs)
- `multiparent_corners` (merge over a parent with a `[condition = …]` group, with the
  variable unset (group skipped in parent and merge) and set (checked, never certified);
  merge over a parent with `sessions` and `document_theories`; `B + C` and `C + B` give
  the same theorems, `cached_proof` on the re-loaded side)
- `normalize` (session `MPT_NRM`: `NA` imports `NK`, which declares the user command
  `mysection :: document_heading`; hits after comment, indentation, blank-line and `text`
  edits and inserted `section`/`text`; `-o proof_cache_normalize=false` misses for both
  theories (other key scheme), switching back hits; misses after editing a statement, a
  method, the nonce string, a comment inside `ML ‹…›`, a comment inside a term, the body
  of `mysection`, and the keyword declaration in `NK`; an unclosed comment fails the build
  normally, keys fall back to the raw digest)
- Slow (`--slow`): `fresh` (`build -f` rebuilds Pure, HOL and the session with no lookups,
  still certifies; `-c` afterwards trusts again; about 3.5 minutes; it outdates every heap
  above HOL); `afp_demo` (below, about 3.5 minutes).

## Adding a case

A function `case_<name>()` in `mp-tests/run.py` with the `@case` decorator (`@slow_case`
for slow ones), using `build` (returns rc and output, records `Timing` lines; `env=` for
extra environment variables), `check`, `check_ok`, `check_trusted`, `check_oracles` /
`check_oracle_lists` (reads `oracles.out`, written by the test theory's ML block),
`check_fast`/`check_slow`, `cache_rows`, `edit`/`undo_edit`; new sessions go into
`mp-tests/src/ROOT`. Cases run in definition order and may rely on sessions built by
earlier cases; cache rows accumulate over runs (one per nonce), so count them relative to
the start of the case. Session heaps built by `-b` stay real checks only until a rebuild,
which may trust the cache (a parent heap rebuilt from the cache carries `cached_proof`);
note that without `build_thorough` a change of options alone does not rebuild a session
(use `-c`).

## AFP demonstration

`mp-tests/afp-demo`, run by `mp-tests/run.sh --slow afp_demo` (or just
`mp-tests/run.sh afp_demo`) from a copy in `mp-tests/work/afp-demo`, with the run's nonce in `Demo`, so
that `Demo` is new to the proof cache in every run (a cached `Demo` would give its own
facts `cached_proof`). It needs the AFP for Isabelle2025-2 as session roots: add the AFP
`thys` directory to `$ISABELLE_HOME_USER/ROOTS` of this Isabelle. Registering the AFP as a
component instead (`etc/components`) also loads the AFP tools component, whose
`afp_tools.jar` is rebuilt against this Isabelle's `isabelle.jar` (its build shasum covers
`$ISABELLE_SCALA_JAR`) and reports a version mismatch for a changed identifier; the AFP
admin tools (`isabelle afp_*`) are not needed here.

`Word_Lib` (A) and `Automatic_Refinement` (B), both `HOL + sessions HOL-Library …`, are
combined as developments that refine algorithms down to machine words do (e.g.
`Isabelle_LLVM`). `AFP_Demo_Merge = Word_Lib + Automatic_Refinement + theories Demo`,
baseline `AFP_Demo_Base = Word_Lib + sessions Automatic_Refinement + theories Demo`; `Demo`
imports `Word_Lib.Word_Lib_Sumo` and `Automatic_Refinement.Automatic_Refinement` and proves
`x < y ⟹ (ws, ws) ∈ ⟨Id⟩list_rel ∧ (x::64 word) ≤ y - 1`. The merge re-loads B's chain
beyond A's: 37 theories (B's 32 plus `HOL-Eisbach`, `HOL-ex` and `HOL-Library` theories
not in A's heap). A is built stock (`proof_cache=false`) so that its facts carry no
oracle; B with the cache certifies B's theories. Oracles in `Demo` (checked by the case):
`demo` and B's `list_rel_id_simp`, `fun_relI` carry `cached_proof` with the cache and
nothing with `proof_cache=false`; `demo_word` and A's `word_le_minus_one_leq` carry none.
Commands and results: [benchmarks.md](benchmarks.md#afp-pair-mp-testsafp-demo).
