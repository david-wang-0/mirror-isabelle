theory T imports MPT_C.Y begin

lemma t: "fy n + fy m > 1" using fy_pos[of n] fy_pos[of m] by linarith

lemma t2: "fy n > 0" by (simp add: fy_def)

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles [Proof_Context.get_thm \<^context> name] |> map (#1 o #1) |> commas;
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]")
        ["t", "t2", "fy_pos", "slow_y1", "fy_ge"]) ^ "\n")
\<close>

end
