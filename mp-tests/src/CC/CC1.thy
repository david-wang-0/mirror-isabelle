theory CC1 imports CC0 begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- in a [condition = MPT_COND] group *)

lemma fcc_cond: "fcc n > 3" using fcc_pos[of n] by linarith

end
