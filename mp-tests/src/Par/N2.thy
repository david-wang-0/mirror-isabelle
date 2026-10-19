theory N2 imports MPT_C.Y begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- child of the trusted MPT_C.Y, itself not trusted *)

lemma n2_own: "(m::nat) + 0 = m" by simp

lemma n2_y: "fy n + 1 > 1" using fy_pos[of n] by linarith

end
