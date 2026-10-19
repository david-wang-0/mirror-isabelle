theory IB0 imports MPT_IP.IA begin

ML \<open>val nonce = "@NONCE@"\<close>

lemma ib0: "ia + 1 > 1" using ia_pos by simp

end
