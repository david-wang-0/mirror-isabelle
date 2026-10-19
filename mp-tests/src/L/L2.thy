theory L2 imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>

external_file \<open>l2.txt\<close>

lemma l2: "(n::nat) * 2 = n + n" by simp

end
