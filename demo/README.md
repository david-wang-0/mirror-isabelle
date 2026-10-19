# Demo: matrices meet probability

A session that needs two big libraries on different branches of the session graph:
`Jordan_Normal_Form` (AFP; its heap chain `HOL` → `HOL-Computational_Algebra` →
`HOL-Algebra` → `Jordan_Normal_Form` also carries `Polynomial_Factorization` and friends,
142 MB) and `HOL-Probability` (chain `HOL` → `HOL-Analysis` → `HOL-Probability`, 259 MB +
53 MB). [`Demo.thy`](Merge/Demo.thy) imports `Jordan_Normal_Form_Uniqueness` and
`HOL-Probability.Probability` and proves two small facts that need both sides: a uniformly
random element of a finite group lies in a subgroup with probability 1 / [G : H]
(Lagrange's theorem from `HOL-Algebra`), and a uniformly random upper triangular matrix
from a finite set is singular with the probability of a zero on its diagonal
(`upper_triangular_imp_det_eq_0_iff` from `Jordan_Normal_Form`).

In stock Isabelle the session has one parent, say `Jordan_Normal_Form`, and imports the
other library with `sessions "HOL-Probability"`: every build of it re-checks all of
`HOL-Analysis` and `HOL-Probability` from sources, about 5 minutes with 8 threads. With
`session Demo_Merge = Jordan_Normal_Form + "HOL-Probability"` the merge session
`Jordan_Normal_Form+HOL-Probability` re-loads them once on top of the `Jordan_Normal_Form`
heap with their proofs skipped by the proof cache (`HOL-Analysis` is proof-bound: its
check runs at factor 6.4 on 8 threads), stores a heap, and later builds of `Demo_Merge`
(or of any other session with the same two parents) take seconds.

## Running it

Prerequisites (once; the left parent without the cache, so that its facts carry no
oracle; the right parent with the cache, which certifies its theories):

```
isabelle build -b -o proof_cache=false Jordan_Normal_Form
isabelle build -b HOL-Probability
```

If `HOL-Probability` was already up to date from a build without the proof cache, its
theories are not certified yet: the first merge then shows `0/171 theories trusted`,
checks everything and certifies it, and the next run trusts all 171.

Then `demo/run.sh [ISABELLE_TOOL]` (default: this repository's `bin/isabelle`; inherited
`ISABELLE_*` settings are removed) runs, with `-d demo -v -o threads=8`:

```
isabelle build -c Jordan_Normal_Form+HOL-Probability Demo_Merge                         # merge, cache
isabelle build -c -o proof_cache=false Jordan_Normal_Form+HOL-Probability Demo_Merge    # merge, stock checking
isabelle build -c Demo_Base                                                              # baseline, cache
isabelle build -c -o proof_cache=false Demo_Base                                         # baseline, stock
isabelle build -c Demo_Merge                                                             # child only
```

`-c` on the merge cleans only the merge and `Demo_Merge` (the selected sessions and their
descendants), never the parents. Expected log lines: `Proof cache
Jordan_Normal_Form+HOL-Probability: 171/171 theories trusted` for the merge with the cache
and `Proof cache Demo_Base: 170/171 theories trusted` for the baseline (`Demo` itself may be
new).

Oracle check: `Demo.thy` writes `oracles.out` (git-ignored) next to itself, which
`run.sh` prints. With the cache, facts of the left parent's heap have no oracle, facts of
`HOL-Probability` re-loaded by the merge and the demo lemmas built on them carry
`Pure.cached_proof`; with `proof_cache=false` nothing does:

```
group.lagrange: []
upper_triangular_imp_det_eq_0_iff: []
prob_space_uniform_count_measure: [Pure.cached_proof]
measure_uniform_count_measure: [Pure.cached_proof]
group.uniform_prob_subgroup: [Pure.cached_proof]
uniform_prob_singular: [Pure.cached_proof]
```

## Results

Two runs of `run.sh` on 2026-10-19, laptop (Intel i9-13950HX, 64 GB), `-o threads=8`,
machine otherwise idle. "Wall-clock" is the whole `isabelle build` command (including
about 13 s of start-up and session-structure work with the AFP); "session" is its
`Finished` line (elapsed / cpu, including heap loading and saving), from run 1.

| build | wall-clock (run 1, run 2) | session: elapsed / cpu | trusted |
|---|---|---|---|
| merge, proof cache | 118 s, 122 s | merge 1:37 / 4:09 | 171/171 |
| merge, `proof_cache=false` | 334 s, 339 s | merge 5:09 / 30:21 | — |
| baseline (`sessions`), proof cache | 101 s, 97 s | `Demo_Base` 1:23 / 3:43 | 170/171, 171/171 |
| baseline (`sessions`), `proof_cache=false`: **stock** | 318 s, 305 s | `Demo_Base` 4:58 / 31:09 | — |
| `Demo_Merge` again, merge heap current | 16 s, 16 s | `Demo_Merge` 0:03 / 0:03 | 1/1 |

Reading: stock Isabelle spends about 5.2 minutes on every build of the combining session.
The merge with the proof cache takes 2 minutes once (including storing its 149 MB heap)
and then 16 s per rebuild of `Demo_Merge` (other sessions on the same two parents reuse
the merge heap as well): 3.2 minutes saved on the first build, 5 minutes on every later
one. The proof cache alone (baseline with the cache) already brings each build down to 1.6
minutes; the merge makes that a one-off. Without the cache the merge is no faster than
stock (it checks the same theories). The other stock orientation, `HOL-Probability +
sessions Jordan_Normal_Form`, re-checks the `Jordan_Normal_Form` side instead: 4.5 minutes
wall-clock, 2.4 with the cache (measured as the merge
`HOL-Probability+Jordan_Normal_Form`, see
[benchmarks](../docs/multiparent/benchmarks.md#demo)).

Parents, built once (`Finished` lines, `proof_cache=false`, partly while other builds ran):
`HOL-Analysis` 6:34, `HOL-Probability` 0:59; `HOL-Computational_Algebra` 0:50,
`HOL-Algebra` 1:38, `Jordan_Normal_Form` 3:29.
