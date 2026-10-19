# Isabelle2025-2 with multi-parent sessions and a proof cache

An **experimental** fork of the [Isabelle2025-2](https://isabelle.in.tum.de) release
(on the official GitHub mirror) with two additions to `isabelle build`:

- **Multi-parent sessions**: `session D = B + C + …` builds on several parent sessions.
  The heap chain stays linear: synthesized *merge sessions* (`"B+C"`) re-load the theories
  of the right parent's chain on top of the left parent's heap.
- **Per-theory proof cache**: a theory whose content (sources, imports, content options,
  ML system) was checked with real proofs by an earlier successful build is loaded with
  its proofs skipped, via the new oracle `Pure.cached_proof`. Merges rely on it, and so do
  `sessions` imports and rebuilt sessions.

```
session Utils = HOL + theories Lists
session Algebra = HOL + theories Groups
session App = Utils + Algebra +
  theories Main_App          (* may import Utils.Lists and Algebra.Groups *)
```

Headline (8 threads, laptop): re-loading all of `HOL-Library` on top of `HOL-Cardinals`
(merge `HOL-Cardinals+HOL-Library`) takes 39 s elapsed / 136 s cpu with the proof cache,
77 s / 485 s without it. See [benchmarks](docs/multiparent/benchmarks.md), including an AFP
pair where the cache cuts cpu time by a factor of 3 but hardly the elapsed time.

## Trying it

- **Overlay on a release** (how it was developed): unpack Isabelle2025-2, copy this
  branch's `src/Pure` files, `etc/options` and `etc/build.props` over it (`git diff
  8d9ad3f298 isabelle2025-2-multiparent --stat -- src etc` lists them), and preferably set
  `etc/ISABELLE_IDENTIFIER` to e.g. `Isabelle2025-2-mp` so that heaps and the proof cache
  stay apart from an unmodified installation. The next `isabelle` call rebuilds
  `isabelle.jar` from the changed Scala sources.
- **From this repository**: as in Isabelle's [README_REPOSITORY](README_REPOSITORY), but
  without Mercurial: `Admin/init -I Isabelle2025-2-mp` (components, identifier, Scala build).
- Then `isabelle build -b HOL` once (Pure's ML sources changed, so every heap is rebuilt),
  and use `session D = B + C + …` in your ROOT files. `-o proof_cache=false` gives stock
  behaviour.

## Documentation
- [Design](docs/multiparent/design.md): merge sessions, session graphs, semantics, soundness
- [Proof cache](docs/multiparent/proof-cache.md): key, database, options, oracle, limits
- [Benchmarks](docs/multiparent/benchmarks.md): timing tables and the exact commands
- [Testing](docs/multiparent/testing.md): the `mp-tests` suite and the AFP demonstration
- [Follow-ups](docs/multiparent/followups.md): open points

## Status and limits
- Experimental, Isabelle2025-2 only. Test suite: 173 assertions plus two slow cases, all
  passing (2026-10-19).
- A merge re-runs everything except proofs (definitions, datatypes, ML, tool setup), so
  the saving is proportional to proof time; it re-loads every theory of the further
  parents' chains that the first parent's heap lacks (list the biggest parent first).
- Skipped proofs are visible as the `Pure.cached_proof` oracle; GUI use (`-R D` in
  Isabelle/jEdit or Isabelle/VSCode) and distributed builds are untested.

## Licence and authorship
Isabelle's own [README](README), [COPYRIGHT](COPYRIGHT) and sources are unchanged apart from
the files above; the changes are under the same BSD-style licence (see COPYRIGHT). They
were implemented by Claude Opus 5.5 agents under the direction of David Wang.
