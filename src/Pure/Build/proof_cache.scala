/*  Title:      Pure/Build/proof_cache.scala

Proof cache of "isabelle build" (Isabelle2025-2-mp, see also Pure/proof_cache.ML):
theories that an earlier build checked with real proofs are identified by a
content key over their sources, imports and options; when loaded from sources
again with the same key, their proofs are skipped (oracle "cached_proof").
*/

package isabelle


object Proof_Cache {
  /* theory keys */

  def theory_key(
    theory: String,
    sources: List[SHA1.Digest],
    imports: List[SHA1.Digest],
    options: Options
  ): SHA1.Digest = {
    val content_options =
      (for (opt <- options.iterator if opt.for_content) yield opt.name + "=" + opt.value)
        .toList.sorted
    SHA1.digest(
      (theory, Isabelle_System.getenv("ML_IDENTIFIER"), sources.map(_.toString),
        imports.map(_.toString).sorted, content_options).toString)
  }

  // keys of the theories of a session (in import order), added to those of its heap chain
  def theory_keys(
    keys0: Map[String, SHA1.Digest],
    entries: List[Document.Node.Entry],
    theory_options: Map[Document.Node.Name, Options],
    loaded_files: List[(String, List[Path])],
    check_sources: List[Path] => List[(Path, SHA1.Digest)]
  ): Map[String, SHA1.Digest] = {
    val files = loaded_files.toMap
    entries.foldLeft(keys0) {
      case (keys, entry) =>
        val name = entry.name
        val sources =
          check_sources((name.path :: files.getOrElse(name.theory, Nil)).map(_.expand))
        val imports = entry.header.imports.map(a => keys.get(a.theory))
        if (imports.forall(_.isDefined)) {
          keys + (name.theory ->
            theory_key(name.theory, sources.map(_._2), imports.flatten, theory_options(name)))
        }
        else keys
    }
  }

  // theory group options that make the build check real proofs
  def certifies(options: Options): Boolean =
    !options.bool("skip_proofs") && !options.bool("quick_and_dirty") &&
      options.string("condition").isEmpty


  /* database */

  object private_data extends SQL.Data("isabelle_proof_cache") {
    val database: Path = Path.explode("$ISABELLE_HOME_USER/proof_cache.db")

    override lazy val tables: SQL.Tables = SQL.Tables(Theories.table)

    object Theories {
      val theory_name = SQL.Column.string("theory_name").make_primary_key
      val key = SQL.Column.string("key").make_primary_key
      val session_name = SQL.Column.string("session_name")
      val date = SQL.Column.date("date")

      val table = make_table(List(theory_name, key, session_name, date), name = "theories")
    }

    def read_keys(db: SQL.Database, theories: List[String]): Set[(String, String)] =
      db.execute_query_statement(
        Theories.table.select(List(Theories.theory_name, Theories.key),
          sql = SQL.where(Theories.theory_name.member(theories))),
        Set.from[(String, String)],
        res => (res.string(Theories.theory_name), res.string(Theories.key)))

    def write_keys(db: SQL.Database, session_name: String, keys: List[(String, String)]): Unit = {
      val date = Date.now()
      for ((theory, key) <- keys) {
        db.execute_statement(Theories.table.delete(
          sql = SQL.where(SQL.and(Theories.theory_name.equal(theory), Theories.key.equal(key)))))
      }
      db.execute_batch_statement(Theories.table.insert(), batch =
        for ((theory, key) <- keys) yield { (stmt: SQL.Statement) =>
          stmt.string(1) = theory
          stmt.string(2) = key
          stmt.string(3) = session_name
          stmt.date(4) = date
        })
    }
  }

  // theories (with their keys) that were certified before; one database user per JVM
  def lookup(theories: List[(String, SHA1.Digest)]): List[String] = synchronized {
    if (theories.isEmpty) Nil
    else {
      using(SQLite.open_database(private_data.database)) { db =>
        val known =
          private_data.transaction_lock(db, create = true, label = "Proof_Cache.lookup") {
            private_data.read_keys(db, theories.map(_._1))
          }
        for ((theory, key) <- theories if known((theory, key.toString))) yield theory
      }
    }
  }

  def write(session_name: String, theories: List[(String, SHA1.Digest)]): Unit = synchronized {
    if (theories.nonEmpty) {
      using(SQLite.open_database(private_data.database)) { db =>
        private_data.transaction_lock(db, create = true, label = "Proof_Cache.write") {
          private_data.write_keys(db, session_name,
            theories.map({ case (theory, key) => (theory, key.toString) }))
        }
      }
    }
  }


  /* build session: Build_Job */

  class Build_Session(info: Sessions.Info, base: Sessions.Base, progress: Progress) {
    val enabled: Boolean = info.options.bool("proof_cache")

    // theories loaded from sources, with their group options and keys
    private val theories: List[(String, Options, Option[SHA1.Digest])] =
      for ((name, options) <- base.used_theories)
        yield (name.theory, options, base.theory_keys.get(name.theory))

    private def error(exn: Throwable): Unit =
      progress.echo_warning("Proof cache " + info.name + ": " + Exn.message(exn))

    val cached_theories: List[String] =
      if (!enabled) Nil
      else {
        try { lookup(theories.collect({ case (a, _, Some(key)) => (a, key) })) }
        catch { case exn: Throwable if !Exn.is_interrupt(exn) => error(exn); Nil }
      }

    if (enabled && theories.nonEmpty) {
      progress.echo("Proof cache " + info.name + ": " + cached_theories.length + "/" +
        theories.length + " theories trusted", verbose = cached_theories.isEmpty)
    }

    // exchange with the ML process: files "cached" (input) and "skipped" (output)
    private val dir: Option[Path] =
      if (!enabled) None
      else {
        val dir = File.path(Isabelle_System.tmp_dir("proof_cache"))
        File.write(dir + Path.basic("cached"), terminate_lines(cached_theories))
        Some(dir)
      }

    def env: List[(String, String)] =
      dir.map(dir => "ISABELLE_PROOF_CACHE" -> File.standard_path(dir)).toList

    // certify the theories checked with real proofs, after a successful build
    def finish(ok: Boolean): Unit =
      for (dir <- this.dir) {
        if (ok) {
          val cached = cached_theories.toSet
          val skipped_path = dir + Path.basic("skipped")
          val skipped =
            if (skipped_path.is_file) split_lines(File.read(skipped_path)).filter(_.nonEmpty).toSet
            else Set.empty[String]
          val certified =
            if (!skipped.forall(a => theories.exists(_._1 == a))) Nil  // oracle outside session
            else {
              theories.collect({ case (a, options, Some(key))
                if !cached(a) && !skipped(a) && certifies(options) => (a, key) })
            }
          try { write(info.name, certified) }
          catch { case exn: Throwable if !Exn.is_interrupt(exn) => error(exn) }
        }
        Isabelle_System.rm_tree(dir)
      }
  }
}
