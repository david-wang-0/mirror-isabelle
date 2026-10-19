theory MC0 imports MPT_B.X MPT_CC.CC0 begin

lemma mc0: "fx n + fcc m > 4" using fx_pos[of n] fcc_pos[of m] by linarith

end
