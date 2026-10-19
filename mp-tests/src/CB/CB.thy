theory CB imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- built concurrently with the other of CA/CB *)

lemma CB_1: "((p::int) + q + r)^4 = ((r + q) + p)^4" by (simp add: algebra_simps power_def)

end
