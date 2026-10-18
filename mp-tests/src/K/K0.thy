theory K0 imports MPT_D.Z MPT_F.V begin

lemma k: "fw n > 0" by (rule fw_pos)

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles [Proof_Context.get_thm \<^context> name] |> map (#1 o #1) |> commas;
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]")
        ["k", "v", "only_x", "fx_pos", "fy_pos", "fw_pos"]) ^ "\n")
\<close>

end
