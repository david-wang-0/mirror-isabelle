theory Z imports MPT_B.X MPT_C.Y begin

lemma both: "fx n + fy m > 1" using fx_pos[of n] fy_pos[of m] by linarith

lemma only_x: "fx n + fx m > 1" using fx_pos[of n] fx_pos[of m] by linarith

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles [Proof_Context.get_thm \<^context> name] |> map (#1 o #1) |> commas;
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]")
        ["both", "only_x", "fx_pos", "fy_pos", "slow_y1"]) ^ "\n")
\<close>

end
