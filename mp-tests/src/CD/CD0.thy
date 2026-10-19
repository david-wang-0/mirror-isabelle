theory CD0 imports MPT_E.W begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- session with document_theories *)

lemma cd0: "fw n + 1 > 1" using fw_pos[of n] by linarith

end
