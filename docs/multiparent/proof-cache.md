# Per-theory proof cache

Whenever `isabelle build` loads a theory T from sources (theories of non-ancestor sessions
imported via `sessions`, the theories a [merge session](design.md) re-loads, or simply the
theories of a session that is rebuilt) and an earlier build already checked T with real
proofs and identical content, T is loaded with its proofs skipped. This replaces a
blanket `skip_proofs=true` for merge sessions: a theory that was never verified is never
skipped.

## Key

`Proof_Cache.theory_key`, computed in `Sessions.Deps.load` for every theory of every
session when sources are inlined (i.e. in builds): SHA1 over the key scheme
(`KEY_VERSION`, currently `2`, and `normalize=true|false`), the theory's long name,
`ML_IDENTIFIER`, the digests of the theory file and of its loaded files (`ML_file` etc.),
the keys of its imports, and all options with tag `content` of the theory's group, as
`name=value` (among them `skip_proofs`, `quick_and_dirty`, `record_proofs`, `condition`).
Version 2 (normalised keys) replaced version 1 (raw digests only): the first build after
the update re-checks and re-certifies every theory once.

**Normalised theory digest** (`Proof_Cache.normalized_digest`; with `proof_cache` and
`proof_cache_normalize`, both default): the theory file is read as the ML process reads it
(UTF-8, symbols not decoded) and tokenised by `Token.explode` with the theory's own outer
syntax (`Dependencies.get_syntax`: Pure, the imports' headers and its own header, as for
the ML process). Dropped are white space, comments (`(* … *)`, `\<comment> \<open>…\<close>`, `\<^cancel>`,
`\<^latex>`, `\<^marker>`), and the spans of the document commands of Pure (`chapter`,
`section`, …, `subparagraph`, `text`, `txt`, `text_raw`, if declared with a document kind):
the command and its arguments up to the next command. The digest is SHA1 over the
remaining tokens as `kind:source`, separated by NUL. So comment, white-space and prose
edits keep the key; any other token change (statements, proofs, ML code, strings) changes
it. Fallback to the raw file digest (still under `normalize=true`) when the lexer reports
an error token (e.g. an unclosed comment or string), when the file contains the Unicode
form of a cartouche or comment delimiter (`‹`, `›`, `―`, …: the Scala lexer accepts them,
the ML lexer does not), or on any exception. Loaded files always use the raw digest.
Theory files are tokenised in parallel; `build -n -v HOL` takes about 1 s longer
(~5 s instead of ~4 s on a loaded machine).

Imports from the heap chain contribute the key computed for their own session, so the key
is a pure content hash, recursively over all ancestors down to theory `Pure`, whose loaded
files are all Pure ML sources (any change of Pure invalidates every key). A theory with an
import without key gets no key. All content options rather than a hand-picked subset:
Isabelle itself declares these as affecting a session's content; the price is misses
between sessions with different content options (e.g. `print_mode`), which is rare.
`document` is not a content option, so merges (`document=false`) hit.

## Database

SQLite `$ISABELLE_HOME_USER/proof_cache.db`, table `isabelle_proof_cache_theories`
(`theory_name`, `key`, `session_name`, `date`; primary key `theory_name, key`). Rows are
never deleted (one per checked content version); deleting the file resets the cache.
Concurrent build processes share the file: a lookup or write that SQLite rejects as busy
(two deferred transactions upgrading to write locks) is retried up to 20 times after a
random 50–300 ms delay; any other database error is a warning (`### Proof cache S: …`),
and the build goes on without the cache (a failed write only loses certifications).

## Build

`Proof_Cache.Build_Session`, hooked into `Build_Job`: at job start the keys of the
session's `used_theories` (theories loaded from sources) are looked up; the hits are the
trusted theories, logged as `Proof cache S: N/M theories trusted` (only with `-v` when
N = 0), and handed to the ML process in a temporary directory named by the environment
variable `ISABELLE_PROOF_CACHE`.

After a successful build (`process_result.ok`) every used theory is certified (row
written) that

1. was not trusted in this build (a cached skip never re-certifies),
2. has group options `skip_proofs=false`, `quick_and_dirty=false`, no `condition`, and
3. contains no deliberate cheating: `sorry`/`cheating` under `declare [[quick_and_dirty]]`
   or `Goal.prove_sorry` in quick-and-dirty mode (a cached load would skip such a proof
   and relabel it `cached_proof`).

Tools that build `skip_proof` oracle theorems internally (`Skip_Proof.make_thm`, direct
`Skip_Proof.cheat_tac`: Meson's `cheat_choice`, quickcheck generators, the predicate
compiler) do not block certification: they do the same in a cached load and keep their
`skip_proof` oracle there. All 116 HOL and 148 HOL-Library theories are certified. If
cheating is recorded for a theory outside the session's used theories, nothing is
certified.

`build -f` (fresh build) does no lookups (everything is checked) but still certifies; as
in stock Isabelle it rebuilds the whole chain down to Pure (`build -f MPT_W`: Pure, HOL and
`MPT_W`, about 3 minutes, log lines `Proof cache HOL: 0/116 theories trusted (fresh
build)`), which outdates every heap above HOL; to re-check a single session use
`-c -o proof_cache=false S`.

## ML side and the oracle

`Pure/proof_cache.ML`, hooks marked `MP:`. `Resources.begin_theory` sets the config flag
`Proof_Cache.cached_proof` for trusted theories (reset at theory end, so it is never
inherited); `Goal.skip_proofs_enabled ctxt` is the `skip_proofs` option or that flag (not
with proof terms enabled), consulted in `Goal.prove_common`, Isar terminal proofs and the
toplevel (`document=false` only), exactly like `skip_proofs`. These skip paths use
`Proof_Cache.skip_tac` (oracle `Pure.cached_proof` when the flag is set, else
`Skip_Proof.cheat_tac`): `goal.ML` directly, the terminal and toplevel skips via
`Method.cheating true`. Deliberate cheating (`Method.cheating false`, `Goal.prove_sorry`)
goes through `Proof_Cache.sorry_tac`, which appends its theory to the file `skipped` in the
exchange directory.

## Option

`proof_cache` (default `true`, tag `build`, not content, so heaps are unaffected):
`isabelle build -o proof_cache=false` is stock behaviour (no lookup, no flag, no writes).
`build -c` only cleans heaps (a rebuild uses the cache); `build -f` or
`-o proof_cache=false` force full re-checking.

`proof_cache_normalize` (default `true`, tag `build`): normalised theory digests (see
[Key](#key)); `false` gives raw digests (version-1 behaviour under the version-2 scheme).
The value is part of every key, so keys of the two schemes never match: switching
re-checks once. Like `proof_cache`, it does not make an up-to-date session rebuild.

## Soundness

A hit for T means that an earlier, successful build checked all proofs of T (without the
`skip_proof` oracle inside T) against imports with identical keys: identical sources
recursively, identical content options, the same ML system and Pure. Elaboration is
deterministic in these inputs (the same assumption as stock up-to-date checks of heaps,
which use the same notion of sources), so the proofs would succeed again and establish
the same statements. The trusted set need not be closed under imports: an import I that
misses (never certified, or certified only under other options) is checked now, or
skipped by an explicit option with the `skip_proof` oracle; T's proofs relative to I's
statements stay valid, and the oracles of T's theorems still show any skip in I. At kernel
level every skipped proof is a `Pure.cached_proof` oracle theorem (`thm_oracles`,
`Thm_Deps.all_oracles`), never silent.

Normalised digests identify sources that differ only in material without logical effect.
White space and comments are discarded by the ML lexer itself (markers only declare
things on the presentation context). The dropped document commands are Pure's own
(`Pure/pure_syn.ML`: `Keyword.vacuous` kinds, output via `Document_Output.document_output`
into the presentation, theory unchanged); a command name cannot be defined twice, so
these spans cannot do anything else. User commands declared with a document kind
(`keywords "foo" :: document_heading`) may be implemented by arbitrary ML and are kept.
Every command, a dropped one included, still runs in a cached load: a broken antiquotation
fails as before. The keyword tables are those the ML process uses (Pure, the imports'
headers and the theory's own header). Lexer error tokens, Unicode delimiters (lexed
differently by Scala and ML) and exceptions fall back to the raw digest. `KEY_VERSION` and
the option value are part of the key, so keys of different schemes never cross-match.
Source positions shift under normalised edits: only ML code inspecting its own position
could observe that, which is deliberate cheating like the other ML side channels below.

## Limits

- Undeclared inputs (files read by ML without load commands, environment variables,
  external tools) are tracked as weakly as by stock heap up-to-date checks.
- Normalisation is outer-syntax only: comments inside ML cartouches (`ML ‹(* c *) …›`),
  inside terms (`‹… \<comment> ‹c››`) and in loaded files still count, as does the
  text of user-declared document commands.
- Clean rebuilds use the cache too: `build -c S` re-checks nothing that was checked before
  (use `-f` or `-o proof_cache=false` to re-check).
- The toplevel skips whole proofs only with `document=false`; with document output only
  the tactic and terminal proofs are skipped. Schematic goals and `record_proofs` sessions
  are not skipped.
- The oracle trail stops at a cached proof: a lemma whose real proof used `skip_proof`
  facts (e.g. predicate compiler rules) carries only `cached_proof` in a cached load
  (`cached_proof` stands for the earlier check together with whatever it depended on).
- Cheating hidden in ML (a tactic calling `Skip_Proof.cheat_tac` inside a skippable proof)
  is not recorded.
- Heap-chain imports contribute keys computed under the current options; without
  `build_thorough` a changed content option does not rebuild an ancestor heap (stock
  behaviour), so a child theory can be certified under a key that assumes the new options
  although it was checked against the stale heap. Use `build_thorough` (or `-c` the
  ancestors) when changing content options; see [follow-ups](followups.md).
- The database is never cleaned up. The exchange directory is local to the build host
  (distributed builds untested).
