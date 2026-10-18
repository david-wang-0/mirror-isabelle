theory V imports MPT_B.X MPT_C.Y MPT_E.W begin

lemma v: "fx n + fy m + fw k > 2" using fx_pos[of n] fy_pos[of m] fw_pos[of k] by linarith

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles [Proof_Context.get_thm \<^context> name] |> map (#1 o #1) |> commas;
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]")
        ["v", "fx_pos", "fy_pos", "fw_pos"]) ^ "\n")
\<close>

end
