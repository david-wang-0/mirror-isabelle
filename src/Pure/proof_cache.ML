(*  Title:      Pure/proof_cache.ML

Proof cache of "isabelle build" (Isabelle2025-2-mp, see also
Pure/Build/proof_cache.scala): theories that an earlier build checked with real
proofs and identical content are loaded with proofs skipped, via the oracle
"cached_proof". The build passes a directory in ISABELLE_PROOF_CACHE: its file
"cached" lists the trusted theories; the file "skipped" receives the theories
that invoke the oracle "skip_proof" (they are not certified for the cache).
*)

signature PROOF_CACHE =
sig
  val cached_proof: bool Config.T
  val enabled: Proof.context -> bool
  val begin_theory: string -> theory -> theory
  val make_thm_cterm: cterm -> thm
  val skipped: thm -> thm
end;

structure Proof_Cache: PROOF_CACHE =
struct

(* build directory *)

fun build_dir () = getenv "ISABELLE_PROOF_CACHE";

(*state is tagged by the build directory: values stored in a heap are never reused*)
val cached_theories = Synchronized.var "Proof_Cache.cached_theories" ("", Symset.empty);
val skipped_theories = Synchronized.var "Proof_Cache.skipped_theories" ("", Symset.empty);

fun cached_theory name =
  (case build_dir () of
    "" => false
  | dir =>
      Synchronized.change_result cached_theories (fn (dir0, set0) =>
        let
          val set =
            if dir = dir0 then set0
            else Symset.make (split_lines (File.read (Path.explode dir + Path.basic "cached")));
        in (Symset.member set name, (dir, set)) end));


(* theory flag *)

val cached_proof = Config.declare_bool ("cached_proof", \<^here>) (K false);

fun enabled ctxt = Config.get ctxt cached_proof andalso not (Proofterm.any_proofs_enabled ());

fun begin_theory name = Config.put_global cached_proof (cached_theory name);

(*the flag is never inherited by importing theories*)
val _ =
  Theory.setup (Theory.at_end (fn thy =>
    if Config.get_global thy cached_proof
    then SOME (Config.put_global cached_proof false thy) else NONE));


(* oracles *)

val (_, make_thm_cterm) =
  Theory.setup_result (Thm.add_oracle (Binding.make ("cached_proof", \<^here>), I));

fun skipped thm =
  (case build_dir () of
    "" => thm
  | dir =>
      let
        val name = Thm.theory_long_name thm;
        val _ =
          Synchronized.change skipped_theories (fn (dir0, set0) =>
            let val set = if dir = dir0 then set0 else Symset.empty in
              if Symset.member set name then (dir, set)
              else
               (File.append (Path.explode dir + Path.basic "skipped") (name ^ "\n");
                (dir, Symset.insert name set))
            end);
      in thm end);

end;
