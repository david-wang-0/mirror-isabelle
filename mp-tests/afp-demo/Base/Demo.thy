theory Demo
  imports Word_Lib.Word_Lib_Sumo Automatic_Refinement.Automatic_Refinement
begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- new to the proof cache in every run: its own facts carry no oracle *)

text \<open>Machine words and refinement relators: one fact from each parent.\<close>

lemma demo: "x < y \<Longrightarrow> (ws, ws) \<in> \<langle>Id\<rangle>list_rel \<and> (x::64 word) \<le> y - 1"
  by (simp add: word_le_minus_one_leq)

lemma demo_word: "x < y \<Longrightarrow> (x::64 word) \<le> y - 1"
  by (rule word_le_minus_one_leq)

lemma demo_rel: "(ws, ws) \<in> \<langle>Id\<rangle>list_rel"
  by simp

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles (Proof_Context.get_thms \<^context> name) |> map (#1 o #1) |> commas;
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines (map (fn n => n ^ ": [" ^ oracles n ^ "]")
        ["demo", "demo_word", "demo_rel", "word_le_minus_one_leq", "list_rel_id_simp",
          "fun_relI"]) ^ "\n")
\<close>

end
