theory NK imports Main keywords "mysection" :: document_heading begin

ML \<open>val nonce = "@NONCE@"\<close>
(* nonce -- declares a user command of a document kind: its spans count for the key *)

ML \<open>
  Outer_Syntax.command \<^command_keyword>\<open>mysection\<close> "user-defined heading"
    (Parse.document_source >> (fn _ => Toplevel.keep (K ())))
\<close>

end
