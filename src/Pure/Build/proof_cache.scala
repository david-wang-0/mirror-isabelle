/*  Title:      Pure/Build/proof_cache.scala

Proof cache of "isabelle build" (Isabelle2025-2-mp, see also Pure/proof_cache.ML):
theories that an earlier build checked with real proofs are identified by a
content key over their sources, imports and options; when loaded from sources
again with the same key, their proofs are skipped (oracle "cached_proof").
*/

package isabelle


object Proof_Cache {
  /* theory keys */

  // version of the key scheme: keys of different versions never match
  val KEY_VERSION = "2"

  def theory_key(
    theory: String,
    sources: List[SHA1.Digest],
    imports: List[SHA1.Digest],
    options: Options,
    normalize: Boolean = false
  ): SHA1.Digest = {
    val content_options =
      (for (opt <- options.iterator if opt.for_content) yield opt.name + "=" + opt.value)
        .toList.sorted
    SHA1.digest(
      (KEY_VERSION, "normalize=" + normalize,
        theory, Isabelle_System.getenv("ML_IDENTIFIER"), sources.map(_.toString),
        imports.map(_.toString).sorted, content_options).toString)
  }


  /* normalized theory sources: without white space, comments and document commands */

  // the document commands of Pure (Pure/pure_syn.ML): their spans only produce document
  // output; user-declared commands of a document kind may do anything and are kept
  val document_commands: Set[String] =
    Set("chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph",
      "text", "txt", "text_raw")

  // Unicode forms of lexically relevant symbols: the Scala lexer accepts them like the
  // symbol names, the ML lexer does not (such sources are left to the raw digest)
  private lazy val decoded_delimiters: List[String] =
    List(Symbol.open_decoded, Symbol.close_decoded, Symbol.comment_decoded,
      Symbol.cancel_decoded, Symbol.latex_decoded, Symbol.marker_decoded)

  // digest of the proper tokens without the keyword and the text argument of Pure's
  // document commands, None for bad input
  def normalized_digest(syntax: Outer_Syntax, text: String): Option[SHA1.Digest] =
    try {
      if (decoded_delimiters.exists(text.contains)) None
      else {
        val keywords = syntax.keywords
        val tokens = Token.explode(keywords, text)
        if (tokens.exists(_.is_error)) None
        else {
          def is_document(tok: Token): Boolean =
            tok.is_command && document_commands(tok.source) &&
              keywords.kinds.get(tok.source).exists(Keyword.document)
          def is_source(tok: Token): Boolean =
            tok.kind == Token.Kind.CARTOUCHE || tok.is_string
          def ends_span(tok: Token): Boolean =
            tok.is_command || keywords.is_before_command(tok)

          // Pure_Syn: cmd [% tag] [(in target)] source [;], so only the command keyword and
          // its first cartouche or string outside of parentheses and tags are dropped; every
          // other token is kept (targets, tags, ";", anything unexpected or unknown to the
          // Scala keyword table, a command modifier like "private" of the next command)
          val NORMAL = 0; val SOURCE = 1; val TARGET = 2; val TAG = 3
          val (proper, _) =
            tokens.foldLeft((List.empty[Token], NORMAL)) {
              case ((result, state), tok) =>
                if (!tok.is_proper) (result, state)
                else if (is_document(tok)) (result, SOURCE)
                else if (state == NORMAL || ends_span(tok)) (tok :: result, NORMAL)
                else if (state == SOURCE && is_source(tok)) (result, NORMAL)
                else {
                  val state1 =
                    if (state == SOURCE && tok.is_keyword("(")) TARGET
                    else if (state == SOURCE && tok.is_keyword("%")) TAG
                    else if (state == TARGET && !tok.is_keyword(")")) TARGET
                    else SOURCE
                  (tok :: result, state1)
                }
            }
          Some(SHA1.digest(
            proper.reverse.map(tok =>
              tok.kind.id.toString + ":" + tok.source.length + ":" + tok.source).mkString))
        }
      }
    }
    catch { case exn: Throwable if !Exn.is_interrupt(exn) => None }

  // theory source text as read by the ML process: UTF-8, symbols not decoded
  def read_theory(resources: Resources, name: Document.Node.Name): String =
    resources.with_thy_reader(name,
      reader => Scan.reader_decode_utf8(Scan.reader_is_utf8(reader), reader.source.toString))

  // keys of the theories of a session (in import order), added to those of its heap chain;
  // normalize: theory files by normalized_digest (fallback: raw digest), loaded files raw
  def theory_keys(
    keys0: Map[String, SHA1.Digest],
    entries: List[Document.Node.Entry],
    theory_options: Map[Document.Node.Name, Options],
    loaded_files: List[(String, List[Path])],
    check_sources: List[Path] => List[(Path, SHA1.Digest)],
    normalize: Boolean = false,
    get_syntax: Document.Node.Name => Outer_Syntax = _ => Outer_Syntax.empty,
    resources: Resources = Resources.bootstrap
  ): Map[String, SHA1.Digest] = {
    val files = loaded_files.toMap
    val normalized: Map[String, SHA1.Digest] =
      if (!normalize) Map.empty
      else {
        Par_List.map((name: Document.Node.Name) =>
          name.theory ->
            (try { normalized_digest(get_syntax(name), read_theory(resources, name)) }
             catch { case exn: Throwable if !Exn.is_interrupt(exn) => None }),
          entries.map(_.name)).collect({ case (a, Some(digest)) => a -> digest }).toMap
      }
    entries.foldLeft(keys0) {
      case (keys, entry) =>
        val name = entry.name
        val theory_source =
          normalized.get(name.theory) match {
            case Some(digest) => List(digest)
            case None => check_sources(List(name.path.expand)).map(_._2)
          }
        val loaded_sources = check_sources(files.getOrElse(name.theory, Nil).map(_.expand))
        val sources = theory_source ::: loaded_sources.map(_._2)
        val imports = entry.header.imports.map(a => keys.get(a.theory))
        if (imports.forall(_.isDefined)) {
          keys + (name.theory ->
            theory_key(name.theory, sources, imports.flatten, theory_options(name),
              normalize = normalize))
        }
        else keys
    }
  }

  // theory group options that make the build check real proofs (only content options can
  // affect the statements established by a successful check: they are part of the key)
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

  // concurrent build processes: SQLite reports a busy database at once when two deferred
  // transactions both want to write (lock upgrade), so retry after a random delay
  private def retry[A](body: => A): A = {
    def attempt(n: Int): A =
      try { body }
      catch {
        case exn: java.sql.SQLException
        if n > 1 && Option(exn.getMessage).exists(msg =>
          msg.contains("SQLITE_BUSY") || msg.contains("SQLITE_LOCKED")) =>
          Time.seconds(0.05 + 0.25 * scala.util.Random.nextDouble()).sleep()
          attempt(n - 1)
      }
    attempt(20)
  }

  // theories (with their keys) that were certified before; one database user per JVM
  def lookup(theories: List[(String, SHA1.Digest)]): List[String] = synchronized {
    if (theories.isEmpty) Nil
    else retry {
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
    if (theories.nonEmpty) retry {
      using(SQLite.open_database(private_data.database)) { db =>
        private_data.transaction_lock(db, create = true, label = "Proof_Cache.write") {
          private_data.write_keys(db, session_name,
            theories.map({ case (theory, key) => (theory, key.toString) }))
        }
      }
    }
  }


  /* build session: Build_Job */

  class Build_Session(
    info: Sessions.Info,
    base: Sessions.Base,
    progress: Progress,
    fresh_build: Boolean = false  // build -f: no lookup, but certify
  ) {
    val enabled: Boolean = info.options.bool("proof_cache")

    // theories loaded from sources, with their group options and keys
    private val theories: List[(String, Options, Option[SHA1.Digest])] =
      for ((name, options) <- base.used_theories)
        yield (name.theory, options, base.theory_keys.get(name.theory))

    private def error(exn: Throwable): Unit =
      progress.echo_warning("Proof cache " + info.name + ": " + Exn.message(exn))

    val cached_theories: List[String] =
      if (!enabled || fresh_build) Nil
      else {
        try { lookup(theories.collect({ case (a, _, Some(key)) => (a, key) })) }
        catch { case exn: Throwable if !Exn.is_interrupt(exn) => error(exn); Nil }
      }

    if (enabled && theories.nonEmpty) {
      progress.echo("Proof cache " + info.name + ": " + cached_theories.length + "/" +
        theories.length + " theories trusted" + if_proper(fresh_build, " (fresh build)"),
        verbose = cached_theories.isEmpty)
    }

    // exchange with the ML process: files "cached" (input) and "skipped" (output: cheating)
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
            if (!skipped.forall(a => theories.exists(_._1 == a))) Nil  // cheating outside session
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
