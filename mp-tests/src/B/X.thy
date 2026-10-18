theory X imports Main begin

definition fx :: "nat \<Rightarrow> nat" where "fx n = n + 1"

lemma fx_pos: "fx n > 0" by (simp add: fx_def)

end
