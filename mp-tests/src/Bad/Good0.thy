theory Good0 imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>

lemma good0: "(n::nat) + 0 = n" by simp

end
