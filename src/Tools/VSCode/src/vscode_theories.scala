/*  Title:      Tools/VSCode/src/vscode_theories.scala

Status of theories managed by the prover, for the "Theories" view of the
client (cf. Tools/jEdit/src/theories_dockable.scala, theories_status.scala).
*/

package isabelle.vscode


import isabelle._


object VSCode_Theories {
  /* internal state */

  sealed case class State(
    nodes_status: Document_Status.Nodes_Status = Document_Status.Nodes_Status.empty,
    domain: Option[Set[Document.Node.Name]] = Some(Set.empty),
    trim: Boolean = false,
    force: Boolean = false,
    last_output: Option[JSON.T] = None
  ) {
    def pending(
      new_domain: Option[Set[Document.Node.Name]],
      new_trim: Boolean,
      new_force: Boolean
    ): State = {
      val domain1 =
        for { a <- domain; b <- new_domain } yield a ++ b
      copy(domain = domain1, trim = trim || new_trim, force = force || new_force)
    }
  }
}

class VSCode_Theories(server: Language_Server) {
  private val state = Synchronized(VSCode_Theories.State())


  /* output */

  private def overall_status(
    nodes_status: Document_Status.Nodes_Status,
    name: Document.Node.Name
  ): Document_Status.Overall_Status =
    if (server.resources.loaded_theory(name)) Document_Status.Overall_Status.ok
    else nodes_status.overall_status(name)

  private def theory_json(
    nodes_status: Document_Status.Nodes_Status,
    name: Document.Node.Name
  ): JSON.T = {
    val resources = server.resources
    nodes_status(name).json ++
      JSON.Object(
        "name" -> name.theory,
        "base_name" -> name.theory_base_name,
        "uri" -> Url.print_file(resources.node_file(name)),
        "overall" -> overall_status(nodes_status, name).toString,
        "required" -> resources.get_model(name).exists(_.node_required))
  }

  private def flush(): Unit = {
    val session = server.session

    val output =
      state.change_result { st =>
        // snapshot inside the critical section: updates arriving later are not lost
        val snapshot = session.snapshot()
        val now = Date.now()
        val nodes_status1 =
          st.nodes_status.update_nodes(now, server.resources, snapshot.state, snapshot.version,
            domain = st.domain, trim = st.trim)

        val theories =
          for {
            name <- snapshot.version.nodes.topological_order
            node_status = nodes_status1(name)
            if !node_status.is_empty && !node_status.suppressed && node_status.total > 0
          } yield theory_json(nodes_status1, name)

        val json = LSP.Theories_Status(session.phase.print, theories)
        val changed = st.force || !st.last_output.contains(json)

        (if (changed) Some(json) else None,
          VSCode_Theories.State(nodes_status = nodes_status1, last_output = Some(json)))
      }

    output.foreach(server.channel.write)
  }

  /*
    Delay.first, not Delay.last: during processing, the session reports
    Commands_Changed more often than vscode_output_delay, so a trailing delay
    would postpone the output until the prover is idle.
  */
  private val delay_output: Delay =
    Delay.first(server.options.seconds("vscode_output_delay"), server.channel.Error_Logger) {
      flush()
    }

  private def update(
    domain: Option[Set[Document.Node.Name]] = None,
    trim: Boolean = false,
    force: Boolean = false
  ): Unit = {
    state.change(_.pending(domain, trim, force))
    delay_output.invoke()
  }


  /* main */

  private val main =
    Session.Consumer[Any](getClass.getName) {
      case _: Session.Phase => update(domain = Some(Set.empty))
      case changed: Session.Commands_Changed =>
        update(domain = Some(changed.nodes), trim = changed.assignment)
    }


  /* client requests */

  def request(): Unit = update(force = true)

  def refresh(): Unit = update(trim = true)


  /* init and exit */

  def init(): Unit = {
    server.session.phase_changed += main
    server.session.commands_changed += main
  }

  def exit(): Unit = {
    server.session.phase_changed -= main
    server.session.commands_changed -= main
    delay_output.revoke()
  }
}
