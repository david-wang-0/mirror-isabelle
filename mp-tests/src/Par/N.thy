theory N imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- new to the proof cache, loaded in parallel with the trusted MPT_C.Y *)

definition fn0 :: "nat \<Rightarrow> nat" where "fn0 n = 3 * n + 2"

lemma n1: "fn0 n > 1" by (simp add: fn0_def)

lemma n2: "((p::int) + q + r)^4 = ((r + q) + p)^4" by (simp add: algebra_simps power_def)

end
