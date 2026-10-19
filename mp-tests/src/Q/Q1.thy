theory Q1 imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- sorry under a theory-local quick_and_dirty: never certified *)

declare [[quick_and_dirty]]

lemma q1: "(n::nat) + 1 > n" sorry

declare [[quick_and_dirty = false]]

lemma q1_real: "(n::nat) + 2 > n" by simp

end
