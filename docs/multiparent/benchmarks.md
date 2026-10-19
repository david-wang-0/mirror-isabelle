# Benchmarks

All numbers were measured on one laptop with `-o threads=8`, on 2026-10-18/19. "Timing"
is the theory-processing `Timing` line of `isabelle build -v` (elapsed / cpu); "total" is
the `Finished` line, which includes heap loading and saving. `isabelle` below is this
repository's `bin/isabelle` (see [testing.md](testing.md) for running it next to another
installation).

## Sessions

The toy sessions are those of the test suite (`mp-tests/src/ROOT`): `MPT_C` proves two
slow `algebra_simps` lemmas, `MPT_S = HOL + sessions MPT_C` re-loads its theory, and the
merge `MPT_B+MPT_C` comes from `MPT_D = MPT_B + MPT_C`. For the library sessions, a
directory with this `ROOT`:

```
session MP_Real in Real = "HOL-Cardinals" + "HOL-Combinatorics" +
  theories T
session MP_Base in Base = "HOL-Cardinals" +
  sessions "HOL-Combinatorics"
  theories T
session MP_Real2 in Real2 = "HOL-Cardinals" + "HOL-Library" +
  theories T2
session MP_Base2 in Base2 = "HOL-Cardinals" +
  sessions "HOL-Library"
  theories T2
```

and `Real/T.thy`, `Base/T.thy` (identical):

```
theory T imports "HOL-Cardinals.Cardinals" "HOL-Combinatorics.Combinatorics" begin
lemma "|UNIV :: nat set| =o natLeq" by (rule card_of_nat)
lemma "card {..<(3::nat)} = 3" by simp
lemma "p permutes S \<Longrightarrow> q permutes S \<Longrightarrow> q \<circ> p permutes S"
  by (rule permutes_compose)
end
```

`Real2/T2.thy`, `Base2/T2.thy` (identical):

```
theory T2 imports "HOL-Cardinals.Cardinals" "HOL-Library.Library" begin
lemma "|UNIV :: nat set| =o natLeq" by (rule card_of_nat)
lemma "size {#a, b, c#} = 3" by simp
end
```

Commands, with `-d DIR -v -o threads=8` on every call (parents `HOL-Cardinals`,
`HOL-Combinatorics` and `HOL-Library` built first, with the cache, so that they are
certified). The measurements were taken interactively, one build at a time, and the
exact invocations were not logged; this sequence reproduces the same builds:

```
isabelle build -b HOL-Cardinals HOL-Combinatorics HOL-Library
isabelle build -c HOL-Cardinals+HOL-Combinatorics HOL-Cardinals+HOL-Library \
  MP_Real MP_Base MP_Real2 MP_Base2
isabelle build -c -o proof_cache=false MP_Base MP_Base2 \
  HOL-Cardinals+HOL-Combinatorics HOL-Cardinals+HOL-Library
```

## Proof cache (current version)

| session | cache on | `proof_cache=false` |
|---|---|---|
| toy `MPT_C` (two slow lemmas, real check) | 18.1 s / 36.0 s | — |
| toy `MPT_S = HOL + sessions MPT_C` (re-loads Y) | 0.18 s / 0.22 s (1/2 trusted) | 18.1 s / 36.2 s |
| toy merge `MPT_B+MPT_C` | 0.08 s (1/1 trusted) | 18.3 s |
| `MP_Base = HOL-Cardinals + sessions HOL-Combinatorics` | 6.2 s / 9.9 s (13/14) | 8.0 s / 44.1 s |
| merge `HOL-Cardinals+HOL-Combinatorics` | 6.2 s / 10.5 s (13/13) | 8.2 s / 43.9 s |
| `MP_Base2 = HOL-Cardinals + sessions HOL-Library` | 34.4 s / 84.4 s (113/114) | 49.1 s / 291.1 s |
| merge `HOL-Cardinals+HOL-Library` | 39.0 s / 136.0 s (148/148) | 77.4 s / 484.6 s |

For comparison: the earlier blanket `skip_proofs` merge (before the proof cache) took
38.2 s / 142.7 s for `HOL-Cardinals+HOL-Library`; re-measured after HOL was rebuilt: 37.7 s
/ 139.1 s and 38.9 s / 141.5 s, i.e. the same within noise. Before tool-internal
`skip_proof` uses stopped blocking certification, 19 HOL-Library theories were never
cached: 58.7 s / 310.8 s, 98/114 for `MP_Base2`. HOL with the cache code (all keys new):
135 s / 497 s.

## Merge sessions with blanket `skip_proofs` (first version, 2026-10-18)

| session | elapsed | cpu |
|---|---|---|
| toy `MP_C` (two slow `algebra_simps` lemmas) | 18.5 s | 36.9 s |
| toy merge `MP_B+MP_C` (same theory, proofs skipped) | 0.09 s | 0.13 s |
| merge `HOL-Cardinals+HOL-Combinatorics` | 6.3 s | 10.7 s |
| baseline `MP_Base` (re-checks foreign theories) | 7.6 s | 42.0 s |
| merge `HOL-Cardinals+HOL-Library` (all HOL-Library theories) | 38.2 s | 142.7 s |
| baseline `MP_Base2` (T2 imports `HOL-Library.Library`) | 50.1 s | 291.8 s |

Heap saving adds about 3–11 s to a merge.

## AFP pair (`mp-tests/afp-demo`)

`Word_Lib` (A) and `Automatic_Refinement` (B) combined; the sessions are described in
[testing.md](testing.md#afp-demonstration). This is the slow test case `afp_demo`, which
runs these commands (in this order; `-d mp-tests/work/afp-demo -v -o threads=8` on every
call, the copy with the run's nonce) and prints the table:

```
isabelle build -c -b -o proof_cache=false Word_Lib Automatic_Refinement
isabelle build -c Automatic_Refinement
isabelle build AFP_Demo_Merge
isabelle build -c -o proof_cache=false Word_Lib+Automatic_Refinement AFP_Demo_Merge
isabelle build -c AFP_Demo_Base
isabelle build -c -o proof_cache=false AFP_Demo_Base
```

Results (2026-10-19):

| build | session | theories elapsed / cpu | total | trusted |
|---|---|---|---|---|
| parent A, `proof_cache=false` | `Word_Lib` | 26.3 s / 133.2 s | 31 s | — |
| parent B, `proof_cache=false` | `Automatic_Refinement` | 13.7 s / 56.3 s | 18 s | — |
| parent B, cache (certifies B) | `Automatic_Refinement` | 12.3 s / 33.9 s | 13 s | 4/38 |
| merge, cache | `Word_Lib+Automatic_Refinement` | 12.1 s / 16.3 s | 16 s | 37/37 |
| merge, `proof_cache=false` | `Word_Lib+Automatic_Refinement` | 12.5 s / 50.7 s | 17 s | — |
| child `AFP_Demo_Merge` (either) | `AFP_Demo_Merge` | 0.3 s / 0.4 s | 1 s | — |
| baseline, cache | `AFP_Demo_Base` | 12.3 s / 16.4 s | 13 s | 35/36 |
| baseline, `proof_cache=false` | `AFP_Demo_Base` | 12.7 s / 51.2 s | 13 s | — |

Reading: the cache cuts the cpu time of re-loading B by a factor of 3 (50.7 → 16.3 s), but
hardly the elapsed time: apparently `Automatic_Refinement`'s elapsed time is a sequential
chain of elaboration that the cache does not skip (ML, tool setup, definitions), and with
8 threads its proofs mostly ran in parallel to that chain. The merge costs about what the
baseline costs (both re-load all of B here, since `Demo` imports B's top theory) and gives
a heap that later sessions can build on without re-loading B again. A merge pays off in
elapsed time when the re-loaded chain is proof-heavy (toy `MPT_C`: 18 s → 0.1 s) or when
cores are scarce; it always re-loads all of C's chain, whereas a `sessions` import loads
only the theories it needs.

## Demo

[`demo/`](../../demo/README.md): `Demo_Merge = Jordan_Normal_Form + "HOL-Probability"`
against the stock `Demo_Base = Jordan_Normal_Form + sessions "HOL-Probability"`, both with
the same `Demo.thy` (imports `Jordan_Normal_Form.Jordan_Normal_Form_Uniqueness` and
`HOL-Probability.Probability`); `demo/run.sh` runs the builds and prints the table.

The pair was chosen by measurement. Candidate merges with a trivial child theory importing
both sides, `-v -o threads=8`, theory-processing `Timing` of the merge session (elapsed /
cpu); "checked" is a run with no trusted theory (equivalent to stock checking; some of
these ran while the test suite was running on the same machine), "cached" a `-c` rerun:

| merge (re-loaded part) | checked | cached | trusted |
|---|---|---|---|
| `HOL-Probability+HOL-Algebra` (`HOL-Algebra`) | 86.8 s / 450 s | 56.7 s / 101 s | 75/75 |
| `HOL-Probability+Jordan_Normal_Form` (`HOL-Algebra`, `Jordan_Normal_Form` and the theories it imports from `Polynomial_Factorization` etc.) | 220.8 s / 1189 s | 106.6 s / 234 s | 168/168 |
| `Jordan_Normal_Form+HOL-Probability` (`HOL-Analysis`, `HOL-Probability`) | 328.2 s / 2086 s | 90.8 s / 238 s | 171/171 |

`HOL-Algebra` alone is too small and its cached re-load is dominated by elaboration (57 s);
`HOL-Analysis` is proof-bound (its own build: 362 s / 2313 s, factor 6.4 on 8 threads),
so skipping its proofs saves most of its elapsed time. Hence `Jordan_Normal_Form` (a
142 MB heap that does not contain `HOL-Analysis`) is the left parent and `HOL-Probability`
the right one. The other orientation is the better stock choice (it re-checks less) but
still loses to either merge with the cache.

Demo results (2026-10-19, two runs of `demo/run.sh`, machine otherwise idle; wall-clock of
the whole `isabelle build` command, which includes about 13 s of start-up; `Finished` line
of the session from run 1):

| build | wall-clock (run 1, run 2) | session: elapsed / cpu | trusted |
|---|---|---|---|
| merge, proof cache | 118 s, 122 s | merge 1:37 / 4:09 | 171/171 |
| merge, `proof_cache=false` | 334 s, 339 s | merge 5:09 / 30:21 | — |
| baseline, proof cache | 101 s, 97 s | `Demo_Base` 1:23 / 3:43 | 170/171, 171/171 |
| baseline, `proof_cache=false` (stock) | 318 s, 305 s | `Demo_Base` 4:58 / 31:09 | — |
| `Demo_Merge` again, merge heap current | 16 s, 16 s | `Demo_Merge` 0:03 / 0:03 | 1/1 |

Theory-processing `Timing` (run 1, run 2): merge with the cache 82.0 s / 216.9 s and
85.8 s / 226.1 s; without 272.8 s / 1738.5 s and 276.7 s / 1768.1 s; baseline with the
cache 81.3 s / 218.0 s and 77.1 s / 193.1 s; stock 295.1 s / 1859.2 s and 282.5 s /
1784.2 s. Commands (`-d demo -v -o threads=8` on every call):

```
isabelle build -b -o proof_cache=false Jordan_Normal_Form
isabelle build -b HOL-Probability
isabelle build -c Jordan_Normal_Form+HOL-Probability Demo_Merge
isabelle build -c -o proof_cache=false Jordan_Normal_Form+HOL-Probability Demo_Merge
isabelle build -c Demo_Base
isabelle build -c -o proof_cache=false Demo_Base
isabelle build -c Demo_Merge
```

(Here `HOL-Probability` was built with `proof_cache=false` too, and the first merge with
the cache, `0/171` trusted, certified its theories.)
