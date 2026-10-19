theory L2 imports Main begin

(* nonce: @NONCE@ *)

external_file \<open>l2.txt\<close>

lemma l2: "(n::nat) * 2 = n + n" by simp

end
