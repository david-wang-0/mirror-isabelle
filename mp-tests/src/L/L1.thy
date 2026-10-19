theory L1 imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>

ML_file \<open>l1.ML\<close>

lemma l1: "(n::nat) + (1::nat) = 1 + n" by simp

end
