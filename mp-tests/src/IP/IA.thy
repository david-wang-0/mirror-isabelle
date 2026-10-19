theory IA imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>

definition ia :: nat where "ia = 1"

lemma ia_pos: "ia > 0" by (simp add: ia_def)

end
