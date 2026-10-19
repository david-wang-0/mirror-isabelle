# Follow-ups

- **Per-heap options record (the `build_thorough` corner).** Keys of heap-chain imports
  are computed under the current options; without `build_thorough` a changed content
  option does not rebuild an ancestor heap, so a child theory can be certified under a key
  that assumes the new options although it was checked against the stale heap (see
  [proof-cache.md](proof-cache.md#limits)). Fix: record the content options each heap was
  built with (e.g. next to the heap's build record) and compute the keys of heap-chain
  imports from that record rather than from the current options.
- **A proof-heavier AFP pair.** In the `Word_Lib` + `Automatic_Refinement` demonstration
  the cache cuts cpu time by a factor of 3 but hardly the elapsed time, because the
  re-loaded chain is dominated by sequential elaboration (see
  [benchmarks.md](benchmarks.md#afp-pair-mp-testsafp-demo)). A pair whose right parent is
  proof-heavy would show the elapsed-time effect on real developments.
- **Port to Isabelle2026** once it is released (currently at release candidate RC4; the
  final release is expected around 2026-10-24). The changes are confined to new files plus
  small hooks marked `MP:` in `src/Pure`, which should make the port mechanical.
- **Heap-merge spike (pending).** Instead of re-loading the right parent's theories, merge
  the Poly/ML heaps (or the theory data they hold) directly; a spike to judge feasibility
  has not been done yet.
- Smaller points: the proof-cache database is never cleaned up; distributed builds
  (exchange directory local to the build host) and the GUI `-R D` path are untested.
