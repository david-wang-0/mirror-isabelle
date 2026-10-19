theory PChk imports N N2 begin

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles [Proof_Context.get_thm \<^context> name] |> map (#1 o #1) |> commas;
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]")
        ["N.n1", "N.n2", "N2.n2_own", "N2.n2_y", "Y.fy_pos"]) ^ "\n")
\<close>

end
