theory IB1 imports IB0 begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- never edited: misses only through its imports *)

lemma ib1: "ia + 2 > 2" using ia_pos by simp

end
