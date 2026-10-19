theory QChk imports Q1 Q2 begin

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles [Proof_Context.get_thm \<^context> name] |> map (#1 o #1) |> commas;
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]")
        ["Q1.q1", "Q1.q1_real", "Q2.q2_raw", "Q2.q2", "Q2.q2_real"]) ^ "\n")
\<close>

end
