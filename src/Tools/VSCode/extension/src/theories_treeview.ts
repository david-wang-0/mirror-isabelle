/*  Status of theories managed by the prover, as a tree view
    (cf. Tools/jEdit/src/theories_dockable.scala).
*/

"use strict";

import { EventEmitter, MarkdownString, ThemeColor, ThemeIcon, TreeDataProvider, TreeItem,
  TreeItemCollapsibleState, TreeView, Uri } from "vscode"
import { LanguageClient } from "vscode-languageclient/node"

import * as lsp from "./lsp"


export const view_type = "isabelle-theories"


/* status presentation */

function plural(n: number, word: string): string
{
  return n + " " + word + (n === 1 ? "" : "s")
}

function is_running(theory: lsp.Theory_Status): boolean
{
  return theory.overall === "pending" && theory.running > 0
}

function status_description(theory: lsp.Theory_Status): string
{
  const failed = theory.failed > 0 ? plural(theory.failed, "error") : ""
  if (theory.overall === "ok") {
    return theory.warned > 0 ? plural(theory.warned, "warning") : "✓"
  }
  else if (theory.overall === "failed") return failed
  else {
    const percentage = theory.percentage + "%"
    return failed ? failed + ", " + percentage : percentage
  }
}

function status_icon(theory: lsp.Theory_Status): ThemeIcon
{
  if (theory.overall === "ok") return new ThemeIcon("pass", new ThemeColor("testing.iconPassed"))
  else if (is_running(theory)) return new ThemeIcon("loading~spin")
  else if (theory.overall === "failed" || theory.failed > 0) {
    return new ThemeIcon("error", new ThemeColor("testing.iconFailed"))
  }
  else return new ThemeIcon("circle-outline")
}

function status_tooltip(theory: lsp.Theory_Status): MarkdownString
{
  const status =
    theory.overall === "pending" ? (is_running(theory) ? "running" : "pending") : theory.overall
  const tooltip = new MarkdownString()
  tooltip.appendMarkdown("theory **")
  tooltip.appendText(theory.name)
  tooltip.appendMarkdown("** (" + status + (theory.canceled ? ", canceled" : "") + ")\n\n")
  tooltip.appendMarkdown([
      "unprocessed: " + theory.unprocessed,
      "running: " + theory.running,
      "warned: " + theory.warned,
      "failed: " + theory.failed,
      "finished: " + theory.finished,
      "processed: " + theory.percentage + "%",
      "consolidated: " + (theory.consolidated ? "yes" : "no")
    ].join("  \n"))
  return tooltip
}


/* tree data provider */

export class Provider implements TreeDataProvider<lsp.Theory_Status>
{
  private _theories: lsp.Theory_Status[] = []
  private _phase = ""
  private _view?: TreeView<lsp.Theory_Status>
  private _language_client?: LanguageClient
  private readonly _changed = new EventEmitter<void>()

  readonly onDidChangeTreeData = this._changed.event

  public init(view: TreeView<lsp.Theory_Status>)
  {
    this._view = view
    view.onDidChangeVisibility(event => { if (event.visible) this.request() })
    this.update_description()
  }

  public setup(language_client: LanguageClient)
  {
    this._language_client = language_client
    language_client.onNotification(lsp.theories_status_type, msg => this.update(msg))
    this.request()
  }

  public request()
  {
    if (this._language_client) {
      this._language_client.sendNotification(lsp.theories_request_type)
    }
  }

  private update_description()
  {
    if (this._view) this._view.description = this._phase ? "Prover: " + this._phase : ""
  }

  private update(msg: lsp.Theories_Status)
  {
    this._phase = msg.phase
    this._theories = msg.theories
    this.update_description()
    this._changed.fire()
  }

  getChildren(element?: lsp.Theory_Status): lsp.Theory_Status[]
  {
    return element ? [] : this._theories
  }

  getTreeItem(theory: lsp.Theory_Status): TreeItem
  {
    const uri = Uri.parse(theory.uri)
    const item = new TreeItem(theory.base_name, TreeItemCollapsibleState.None)
    item.id = theory.uri
    item.resourceUri = uri
    item.description = status_description(theory)
    item.iconPath = status_icon(theory)
    item.tooltip = status_tooltip(theory)
    item.command = { command: "vscode.open", title: "Open Theory", arguments: [uri] }
    return item
  }
}
