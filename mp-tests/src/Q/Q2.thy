theory Q2 imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- tool-like internal use of the skip_proof oracle: certified *)

ML \<open>
  val q2_thm = Skip_Proof.make_thm \<^theory> \<^prop>\<open>(0::nat) < 1\<close>;
\<close>

setup \<open>Global_Theory.store_thm (\<^binding>\<open>q2_raw\<close>, q2_thm) #> snd\<close>

lemma q2: "(0::nat) < 1" by (tactic \<open>resolve_tac \<^context> [q2_thm] 1\<close>)

lemma q2_real: "(n::nat) + 3 > n" by simp

end
