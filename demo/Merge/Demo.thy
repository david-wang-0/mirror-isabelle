theory Demo
  imports Jordan_Normal_Form.Jordan_Normal_Form_Uniqueness "HOL-Probability.Probability"
begin

text \<open>Facts of the left parent (\<open>Jordan_Normal_Form\<close> with \<open>HOL-Algebra\<close> in its
  chain) used together with the uniform probability space on a finite set
  (\<open>HOL-Probability\<close>, built on \<open>HOL-Analysis\<close>).\<close>

text \<open>A uniformly random element of a finite group lies in a subgroup H with probability
  1 / [G : H] (Lagrange's theorem).\<close>

lemma (in group) uniform_prob_subgroup:
  assumes fin: "finite (carrier G)" and H: "subgroup H G"
  shows "prob_space (uniform_count_measure (carrier G))"
    and "measure (uniform_count_measure (carrier G)) H = 1 / card (rcosets H)"
proof -
  show "prob_space (uniform_count_measure (carrier G))"
    using fin by (rule prob_space_uniform_count_measure) auto
  have "0 < card H"
    using H fin by (rule subgroup.finite_imp_card_positive)
  moreover have "card (carrier G) = card (rcosets H) * card H"
    using lagrange[OF H] by (simp add: order_def)
  ultimately show "measure (uniform_count_measure (carrier G)) H = 1 / card (rcosets H)"
    using fin subgroup.subset[OF H] by (simp add: measure_uniform_count_measure)
qed

text \<open>A uniformly random matrix from a finite set of upper triangular matrices is
  singular with the probability of a zero on its diagonal (\<open>Determinant.det\<close>: the
  plain name \<open>det\<close> now refers to the determinant of \<open>HOL-Analysis\<close>).\<close>

lemma uniform_prob_singular:
  fixes S :: "'a :: idom mat set"
  assumes fin: "finite S" and "S \<noteq> {}"
    and S: "\<And>A. A \<in> S \<Longrightarrow> A \<in> carrier_mat n n \<and> upper_triangular A"
  shows "prob_space (uniform_count_measure S)"
    and "measure (uniform_count_measure S) {A \<in> S. Determinant.det A = 0} =
      card {A \<in> S. 0 \<in> set (diag_mat A)} / card S"
proof -
  show "prob_space (uniform_count_measure S)"
    using fin \<open>S \<noteq> {}\<close> by (rule prob_space_uniform_count_measure)
  have "{A \<in> S. Determinant.det A = 0} = {A \<in> S. 0 \<in> set (diag_mat A)}"
    using S upper_triangular_imp_det_eq_0_iff by blast
  then show "measure (uniform_count_measure S) {A \<in> S. Determinant.det A = 0} =
      card {A \<in> S. 0 \<in> set (diag_mat A)} / card S"
    using fin by (simp add: measure_uniform_count_measure)
qed

text \<open>Oracles: none for the facts of the left parent's heap; \<open>Pure.cached_proof\<close> for
  the facts of the right parent that the merge re-loaded with their proofs skipped, and
  for the lemmas above, which use them (with \<open>proof_cache = false\<close>: none at all).
  Written to \<open>oracles.out\<close> next to this file.\<close>

ML \<open>
  fun oracles name =
    Thm_Deps.all_oracles (Proof_Context.get_thms \<^context> name) |> map (#1 o #1);
  val _ =
    File.write (Resources.master_directory \<^theory> + Path.basic "oracles.out")
      (cat_lines
        (["group.lagrange", "upper_triangular_imp_det_eq_0_iff",
          "prob_space_uniform_count_measure", "measure_uniform_count_measure",
          "group.uniform_prob_subgroup", "uniform_prob_singular"]
         |> map (fn name => name ^ ": [" ^ commas (oracles name) ^ "]")) ^ "\n")
\<close>

end
