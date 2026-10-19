theory X imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- MPT_B is checked for real in every run: its facts carry no oracle *)

definition fx :: "nat \<Rightarrow> nat" where "fx n = n + 1"

lemma fx_pos: "fx n > 0" by (simp add: fx_def)

end
