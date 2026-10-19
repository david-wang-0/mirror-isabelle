theory O2 imports MPT_B.X MPT_C.Y begin

lemma O2_both: "fx n + fy m > 1" using fx_pos[of n] fy_pos[of m] by linarith

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles [Proof_Context.get_thm \<^context> name] |> map (#1 o #1) |> commas;
  val names = ["fx_pos", "fy_pos", "fy_ge", "O2_both"];
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]") names) ^ "\n");
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "thms.out")
      (cat_lines (map (fn n =>
        n ^ ": " ^ Print_Mode.setmp [] (Syntax.string_of_term \<^context>)
          (Thm.prop_of (Proof_Context.get_thm \<^context> n))) (take 3 names)) ^ "\n");
\<close>

end
