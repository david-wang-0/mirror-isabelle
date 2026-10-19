/*  Title:      Pure/Build/sessions_multiparent.scala

Multi-parent sessions (Isabelle2025-2-mp): "session D = B + C + ..." keeps a linear
heap chain via synthesized merge sessions "B+C" (parent B, re-loading the theories of
C's chain that are not in B's chain), see MP-README.md.
*/

package isabelle


import scala.collection.mutable


object Sessions_Multiparent {
  import Sessions.{Info, Session_Entry, Chapter_Defs}

  // Build_Process: store the heap of a session that is a heap-chain ancestor of a session in
  // the build (Build_Process.Sessions.store_heap also counts build_prereqs: C of "B+C"
  // would be rebuilt just to store a heap that is never loaded)
  def store_heap(structure: Sessions.Structure, sessions: List[String], name: String): Boolean =
    Sessions.is_pure(name) || {
      val graph = structure.heap_graph
      val parents = sessions.filter(graph.defined).flatMap(graph.imm_preds)
      graph.all_preds(parents).contains(name)
    }

  // session infos with other_parents resolved, plus the synthesized merge sessions
  def make_infos(
    raw_infos: List[Info],
    options: Options,
    options0: Options,
    chapter_defs: Chapter_Defs
  ): List[Info] = {
    val raw_info = raw_infos.map(info => info.name -> info).toMap
    val global_names =
      Thy_Header.bootstrap_global_theories.map(_._1).toSet ++
        raw_infos.flatMap(_.global_theories)

    val merges = new mutable.LinkedHashMap[String, Info]
    def get_info(name: String): Option[Info] = raw_info.get(name) orElse merges.get(name)

    var covered_cache = Map.empty[String, List[String]]
    def covered(name: String, seen: Set[String] = Set.empty): List[String] =
      covered_cache.get(name) match {
        case Some(res) => res
        case None if seen(name) => Nil  // cycle: reported via session graph
        case None =>
          val res =
            get_info(name) match {
              case None => Nil
              case Some(info) =>
                (info.parent.toList ::: info.other_parents ::: info.build_prereqs)
                  .flatMap(covered(_, seen + name)).appended(name).distinct
            }
          covered_cache += (name -> res)
          res
      }

    def qualify(session: String, thy: String): String = {
      val thy_name = Thy_Header.import_name(thy)
      if (Long_Name.is_qualified(thy_name) || global_names(thy_name)) thy_name
      else Long_Name.qualify(session, thy_name)
    }

    def merge(info: Info)(left: String, right: String): String = {
      for (a <- List(left, right) if get_info(a).isEmpty) {
        error("Bad parent session " + quote(a) + " for " + quote(info.name) +
          Position.here(info.pos))
      }
      // heap content of a session: theories of the non-merge sessions it covers
      def content(a: String): List[String] = covered(a).filterNot(get_info(_).get.is_merge)
      val content_left = content(left)
      val content_right = content(right)
      val sessions = content_right.filterNot(content_left.contains)

      if (sessions.isEmpty) left
      else if (content_left.forall(content_right.contains)) right
      else {
        val name = left + "+" + right
        if (raw_info.isDefinedAt(name)) {
          error("Merge session " + quote(name) + " for " + quote(info.name) +
            " clashes with existing session" + Position.here(raw_info(name).pos))
        }
        if (!merges.isDefinedAt(name)) {
          val left_info = get_info(left).get
          val right_info = get_info(right).get
          val merge_options = List("document=false")
          val entry =
            Session_Entry(pos = info.pos, name = name, parent = Some(left),
              description = "Merge of sessions " + quote(left) + " and " + quote(right) +
                " (proofs via proof cache)",
              options = merge_options.map(Options.Spec.make), imports = List(right))
          val info0 =
            Info.make(entry, dir = right_info.dir, options = options, options0 = options0,
              chapter_defs = chapter_defs, chapter = left_info.chapter)
          val theories =
            for {
              a <- sessions
              (opts, thys) <- get_info(a).get.theories
            } yield (opts ++ merge_options.map(Options.Spec.make),
              thys.map({ case (thy, pos) => (qualify(a, thy), pos) }))
          val merge_digest =
            SHA1.digest(sessions.map(a => (a, get_info(a).get.meta_info.toString)).toString)
          merges(name) =
            info0.copy(theories = theories, build_prereqs = List(right),
              meta_info = info0.meta_info ::: SHA1.shasum(merge_digest, "merge_sessions"))
        }
        name
      }
    }

    val infos1 =
      for (info <- raw_infos) yield {
        if (info.other_parents.isEmpty) info
        else {
          try {
            val parent = info.other_parents.foldLeft(info.parent.get)(merge(info))
            info.copy(parent = Some(parent), other_parents = Nil)
          }
          catch {
            case ERROR(msg) =>
              error(msg + "\nThe error(s) above occurred in session entry " +
                quote(info.name) + Position.here(info.pos))
          }
        }
      }
    infos1 ::: merges.valuesIterator.toList
  }
}
