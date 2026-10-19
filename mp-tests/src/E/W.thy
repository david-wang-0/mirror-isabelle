theory W imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- MPT_E is checked for real in every run (merges with MPT_E expect a hit) *)

definition fw :: "nat \<Rightarrow> nat" where "fw n = n + 2"

lemma fw_pos: "fw n > 0" by (simp add: fw_def)

end
