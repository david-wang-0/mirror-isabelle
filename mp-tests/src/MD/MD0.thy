theory MD0 imports MPT_B.X MPT_CD.CD0 begin

lemma md0: "fx n + fw m > 1" using fx_pos[of n] fw_pos[of m] by linarith

end
