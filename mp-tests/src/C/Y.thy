theory Y imports Main begin

ML \<open>val nonce = "@NONCE@"\<close>

definition fy :: "nat \<Rightarrow> nat" where "fy n = 2 * n + 1"

lemma fy_pos: "fy n > 0" by (simp add: fy_def)

text \<open>Slow proofs (about 18 s each): the proof cache should skip them.\<close>

lemma slow_y1: "((p::int) + q + r + s)^6 = ((s + r) + (q + p))^6"
  by (simp add: algebra_simps power_def)

lemma slow_y2: "((p::int) + q + r + t)^6 = ((t + r) + (q + p))^6"
  by (simp add: algebra_simps power_def)

lemma fy_ge: "fy n \<ge> 1" using fy_pos[of n] by linarith

end
