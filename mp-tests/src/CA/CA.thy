theory CA imports Main begin

(* nonce: @NONCE@ -- built concurrently with the other of CA/CB *)

lemma CA_1: "((p::int) + q + r)^4 = ((r + q) + p)^4" by (simp add: algebra_simps power_def)

end
