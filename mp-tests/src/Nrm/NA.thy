theory NA imports NK begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- edited by case_normalize: normalised proof cache keys *)

(* comment: edited by case_normalize *)

text \<open>Body text: edited by case_normalize.\<close>

definition na :: nat where "na = 3"

lemma na_pos: "na > 0"
  by (simp add: na_def)

ML \<open>(* ML comment *) val na_ml = 1\<close>

lemma na_ge: \<open>na \<ge> 1 \<comment> \<open>term comment\<close>\<close>
  unfolding na_def by simp

mysection \<open>Heading body\<close>

context
begin

text \<open>Followed by a command modifier.\<close>
lemma na_ctx: "na \<noteq> 0" by (simp add: na_def)

end

end
