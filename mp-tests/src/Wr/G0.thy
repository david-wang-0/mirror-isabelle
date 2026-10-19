theory G0 imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>

lemma g0: "(n::nat) * 1 = n" by simp

end
