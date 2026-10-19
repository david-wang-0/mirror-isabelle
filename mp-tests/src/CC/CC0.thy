theory CC0 imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>

definition fcc :: "nat \<Rightarrow> nat" where "fcc n = n + 5"

lemma fcc_pos: "fcc n > 4" by (simp add: fcc_def)

end
