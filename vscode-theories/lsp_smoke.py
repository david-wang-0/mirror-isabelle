#!/usr/bin/env python3
"""Smoke test for the Theories sidebar protocol of the Isabelle/VSCode language server.

Usage:  vscode-theories/lsp_smoke.py [-l LOGIC] [-L LOGFILE] [-t TIMEOUT] [--phase1] ISABELLE_HOME

Starts "$ISABELLE_HOME/bin/isabelle vscode_server -l HOL", speaks LSP over stdio, opens
three generated theories A <- B <- C (B contains a failing proof), and checks the
PIDE/theories_status notifications:

  Phase 1: A, B, C are reported in topological order; A ends "ok", B ends "failed".
  Phase 2: theories are not required by default; PIDE/theories_set_required flips C's
           "required"; PIDE/theories_purge keeps C while it is open or required, removes
           it once it is closed and not required, keeps B (open) and A (closed, imported
           by B).

Exits with status 0 on success. The logic's heap must already be built.
"""

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


THEORIES = {
    "A": 'theory A imports Main\nbegin\n\nlemma a: "x = x" by simp\n\nend\n',
    "B": 'theory B imports A\nbegin\n\nlemma b: "False" by simp\n\nend\n',
    "C": 'theory C imports B\nbegin\n\nlemma c: "y = y" by simp\n\nend\n',
}


class Failure(Exception):
    pass


class Server:
    def __init__(self, isabelle_home, logic, logfile):
        args = [str(Path(isabelle_home) / "bin" / "isabelle"), "vscode_server", "-l", logic]
        if logfile:
            args += ["-L", logfile]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        self.messages = queue.Queue()
        self.next_id = 0
        self.stderr = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self):
        out = self.proc.stdout
        while True:
            headers = {}
            while True:
                line = out.readline()
                if not line:
                    self.messages.put(None)
                    return
                line = line.decode("ascii").strip()
                if not line:
                    break
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
            body = out.read(int(headers["content-length"]))
            msg = json.loads(body.decode("utf-8"))
            for m in msg if isinstance(msg, list) else [msg]:
                self.messages.put(m)

    def _read_stderr(self):
        for line in self.proc.stderr:
            self.stderr.append(line.decode("utf-8", "replace"))

    def send(self, msg):
        msg = dict(jsonrpc="2.0", **msg)
        body = json.dumps(msg).encode("utf-8")
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.proc.stdin.flush()

    def notify(self, method, params=None):
        msg = {"method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)

    def request(self, method, params=None):
        self.next_id += 1
        msg = {"id": self.next_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)
        return self.next_id

    def receive(self, deadline):
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise queue.Empty
        msg = self.messages.get(timeout=timeout)
        if msg is None:
            raise Failure("server terminated:\n" + "".join(self.stderr[-30:]))
        return msg


class Client:
    def __init__(self, server, timeout):
        self.server = server
        self.timeout = timeout
        self.status = None  # params of the latest PIDE/theories_status
        self.status_count = 0
        self.diagnostics = {}  # uri -> latest list of diagnostics

    def handle(self, msg):
        method = msg.get("method")
        if method == "PIDE/theories_status":
            self.status = msg["params"]
            self.status_count += 1
            names = [t["base_name"] + ":" + t["overall"] +
                     ("" if t["required"] else "(not required)") + "/" + str(t["percentage"]) + "%"
                     for t in self.status["theories"]]
            print("  theories_status [%s] %s" % (self.status["phase"], " ".join(names)))
        elif method == "textDocument/publishDiagnostics":
            self.diagnostics[msg["params"]["uri"]] = msg["params"]["diagnostics"]
        elif method == "window/logMessage" or method == "window/showMessage":
            text = msg["params"].get("message", "")
            if msg["params"].get("type") == 1:
                print("  server error: " + text)

    def wait_for(self, what, predicate, timeout=None):
        deadline = time.monotonic() + (timeout or self.timeout)
        if predicate(None):
            return
        while True:
            try:
                msg = self.server.receive(deadline)
            except queue.Empty:
                raise Failure("timeout waiting for " + what +
                              "; last theories_status: " + json.dumps(self.status))
            self.handle(msg)
            if predicate(msg):
                return msg

    def expect_no_status(self, what, predicate, window):
        """Observe the status messages for `window` seconds: none may satisfy `predicate`."""
        try:
            self.wait_status(what, predicate, timeout=window)
        except Failure:
            return
        raise Failure("unexpected: " + what)

    def wait_status(self, what, predicate, timeout=None):
        def check(_msg):
            return self.status is not None and predicate(self.theories())
        self.wait_for(what, check, timeout)
        return self.theories()

    def theories(self):
        return {t["uri"]: t for t in self.status["theories"]} if self.status else {}

    def order(self):
        return [t["uri"] for t in self.status["theories"]] if self.status else []


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("isabelle_home")
    parser.add_argument("-l", dest="logic", default="HOL")
    parser.add_argument("-L", dest="logfile", default=None)
    parser.add_argument("-t", dest="timeout", type=float, default=300.0,
                        help="timeout in seconds for each step (default 300)")
    parser.add_argument("--phase1", action="store_true", help="skip the Phase 2 checks")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="theories_smoke_"))
    uris = {}
    for name, text in THEORIES.items():
        path = tmp / (name + ".thy")
        path.write_text(text)
        uris[name] = path.resolve().as_uri()
    names = uris  # theories are identified by their file uri

    print("starting vscode_server (%s), theories in %s" % (args.logic, tmp))
    server = Server(args.isabelle_home, args.logic, args.logfile)
    client = Client(server, args.timeout)
    ok = False
    try:
        init_id = server.request("initialize", {"processId": os.getpid(), "rootUri": None,
                                                "capabilities": {}})
        reply = client.wait_for("initialize reply", lambda m: m is not None and m.get("id") == init_id,
                                timeout=max(args.timeout, 600))
        if "error" in reply:
            raise Failure("initialize failed: " + json.dumps(reply["error"]))
        print("initialized")
        server.notify("initialized", {})

        for name, text in THEORIES.items():
            server.notify("textDocument/didOpen", {"textDocument": {
                "uri": uris[name], "languageId": "isabelle", "version": 1, "text": text}})
        # the caret is in C, like an active editor: C and its imports get checked
        server.notify("PIDE/caret_update", {"uri": uris["C"], "line": 0, "character": 0})
        server.notify("PIDE/theories_request")

        # Phase 1
        client.wait_status("first theories_status", lambda ts: True)
        ts = client.wait_status(
            "A ok and B failed",
            lambda ts: all(names[n] in ts for n in "ABC") and
                       ts[names["A"]]["overall"] == "ok" and ts[names["B"]]["overall"] == "failed")
        order = [n for n in client.order() if n in names.values()]
        if order != [names["A"], names["B"], names["C"]]:
            raise Failure("bad topological order: " + str(order))
        for n in "ABC":
            t = ts[names[n]]
            if t["base_name"] != n or t["uri"] != uris[n]:
                raise Failure("bad name/uri for %s: %s" % (n, json.dumps(t)))
            for key in ("ok", "total", "unprocessed", "running", "warned", "failed", "finished",
                        "canceled", "consolidated", "percentage", "required"):
                if key not in t:
                    raise Failure("missing field %s in %s" % (key, json.dumps(t)))
        if ts[names["B"]]["failed"] < 1:
            raise Failure("B should have failed commands: " + json.dumps(ts[names["B"]]))
        if client.status["phase"] != "ready":
            raise Failure("prover phase should be ready: " + client.status["phase"])
        print("PHASE 1 OK")

        # explicit request yields a (forced) status message even without changes
        count = client.status_count
        server.notify("PIDE/theories_request")
        client.wait_for("forced theories_status", lambda m: client.status_count > count, timeout=30)
        print("FORCED REQUEST OK")

        if not args.phase1:
            # Phase 2: required toggle
            if any(t["required"] for t in client.theories().values()):
                raise Failure("theories should not be required by default")
            server.notify("PIDE/theories_set_required", {"uri": uris["C"], "required": True})
            client.wait_status("C required", lambda ts: ts[names["C"]]["required"])
            server.notify("PIDE/theories_set_required", {"uri": uris["C"], "required": False})
            client.wait_status("C not required", lambda ts: not ts[names["C"]]["required"])
            print("SET_REQUIRED OK")

            # Phase 2: purge -- an open theory is never purged
            server.notify("PIDE/theories_purge")
            client.expect_no_status("open theory C purged", lambda ts: names["C"] not in ts, 10)

            # close C (the editor of B becomes active): while C is required, purge keeps it
            server.notify("PIDE/theories_set_required", {"uri": uris["C"], "required": True})
            client.wait_status("C required", lambda ts: ts[names["C"]]["required"])
            server.notify("PIDE/caret_update", {"uri": uris["B"], "line": 0, "character": 0})
            server.notify("textDocument/didClose", {"textDocument": {"uri": uris["C"]}})
            server.notify("PIDE/theories_purge")
            client.expect_no_status("required theory C purged", lambda ts: names["C"] not in ts, 10)

            # C no longer required: purge removes C, A and B remain
            server.notify("PIDE/theories_set_required", {"uri": uris["C"], "required": False})
            server.notify("PIDE/theories_purge")
            ts = client.wait_status("C purged", lambda ts: names["C"] not in ts)
            if names["A"] not in ts or names["B"] not in ts:
                raise Failure("A and B must remain after purge: " + str(list(ts)))
            if client.diagnostics.get(uris["C"]) != []:
                raise Failure("diagnostics of purged C should be cleared")
            print("PURGE OK")

            # B is still open and imports A: closing A and purging keeps A
            server.notify("textDocument/didClose", {"textDocument": {"uri": uris["A"]}})
            server.notify("PIDE/theories_purge")
            client.expect_no_status("imported theory A purged", lambda ts: names["A"] not in ts, 10)
            print("PURGE RETAINS IMPORTS OK")

        shutdown_id = server.request("shutdown")
        reply = client.wait_for("shutdown reply",
                                lambda m: m is not None and m.get("id") == shutdown_id, timeout=60)
        if "error" in reply:
            raise Failure("shutdown failed: " + json.dumps(reply["error"]))
        server.notify("exit")
        rc = server.proc.wait(timeout=60)
        print("server exit code %d" % rc)
        ok = True
    except Failure as exn:
        print("FAILED: " + str(exn))
    finally:
        if server.proc.poll() is None:
            server.proc.kill()
            server.proc.wait()

    print("SMOKE TEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
