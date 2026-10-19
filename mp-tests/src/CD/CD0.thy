theory CD0 imports MPT_E.W begin

(* nonce: @NONCE@ -- session with document_theories *)

lemma cd0: "fw n + 1 > 1" using fw_pos[of n] by linarith

end
