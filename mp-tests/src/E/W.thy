theory W imports Main begin

definition fw :: "nat \<Rightarrow> nat" where "fw n = n + 2"

lemma fw_pos: "fw n > 0" by (simp add: fw_def)

end
