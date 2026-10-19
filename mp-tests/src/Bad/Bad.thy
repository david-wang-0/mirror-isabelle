theory Bad imports Good0 begin

ML \<open>val nonce = "@NONCE@"\<close>

lemma bad: "(n::nat) + 1 = n" by simp

end
