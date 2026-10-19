#!/usr/bin/env python3
"""Test suite for multi-parent sessions and the proof cache
(see docs/multiparent/testing.md).

Usage: mp-tests/run.sh [-l] [--slow] [--isabelle TOOL] [CASE ...]

The Isabelle tool is TOOL, else $ISABELLE_TOOL, else bin/isabelle of this
repository; it runs with the Isabelle settings variables of the calling
environment removed, so that it computes its own (ISABELLE_HOME etc.).

Copies src/ to work/ (git-ignored), substituting a fresh @NONCE@ so that the
theories carrying it are new to the proof cache, then runs the cases in CASES
order (all, or the given ones) on the normal user heaps of that Isabelle.
Cases registered with @slow_case run only with --slow or when named.
Each assertion prints a PASS or FAIL line; the exit code is 1 if any failed.

Add a case: write a function `case_<name>()` using `build`, `check`, `cache_rows`,
`oracles` etc. and register it with the @case decorator; cases run in definition
order and may rely on sessions that earlier cases built (builds are incremental).
"""

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid


HERE = os.path.dirname(os.path.abspath(__file__))
ISABELLE_HOME = os.path.dirname(HERE)
ISABELLE = os.environ.get("ISABELLE_TOOL") or os.path.join(ISABELLE_HOME, "bin", "isabelle")
SRC = os.path.join(HERE, "src")
WORK = os.path.join(HERE, "work")

BUILD_OPTIONS = ["-o", "threads=8"]

# a cached/merged session must take less than this fraction of the real check
FAST_FACTOR = 0.25
# a session checked in full must take more than this fraction of the real check
SLOW_FACTOR = 0.5

CACHED = "Pure.cached_proof"


# utilities

# inherited settings of another Isabelle installation would override the tool's own
CLEAR_ENV = ["ISABELLE_HOME", "ISABELLE_SETTINGS_PRESENT", "ISABELLE_IDENTIFIER",
             "ISABELLE_HOME_USER", "ISABELLE_TOOL"]


def tool_env(env=None):
    result = {k: v for k, v in os.environ.items() if k not in CLEAR_ENV}
    result.update(env or {})
    return result


def isabelle(*args, env=None):
    proc = subprocess.run([ISABELLE, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, env=tool_env(env))
    return proc.returncode, proc.stdout


def getenv(name):
    return isabelle("getenv", "-b", name)[1].strip()


TIMING = {}  # session -> maximal elapsed seconds of its builds (a real check, not a cached one)


def build_args(*args):
    return ["build", "-d", WORK, "-v", *BUILD_OPTIONS, *args]


def record_timing(out):
    for m in re.finditer(r"^Timing (\S+) \(\d+ threads, ([\d.]+)s elapsed", out, re.M):
        TIMING[m.group(1)] = max(TIMING.get(m.group(1), 0.0), float(m.group(2)))


def build(*args, env=None):
    """isabelle build -d work -v ARGS: (rc, output); records Timing lines"""
    rc, out = isabelle(*build_args(*args), env=env)
    record_timing(out)
    return rc, out


def started(out, session):
    """session was built (or run) in this output"""
    return re.search(r"^(Building|Running) " + re.escape(session) + r" \.\.\.", out, re.M)


def line_index(out, pattern):
    m = re.search(pattern, out, re.M)
    return m.start() if m else -1


def trusted(out, session):
    """(n, m) from 'Proof cache SESSION: n/m theories trusted', or None"""
    m = re.search(r"^Proof cache " + re.escape(session) + r": (\d+)/(\d+) theories trusted",
                  out, re.M)
    return (int(m.group(1)), int(m.group(2))) if m else None


def cache_db():
    return os.path.join(getenv("ISABELLE_HOME_USER"), "proof_cache.db")


def cache_rows(theory=None):
    """rows (theory_name, key, session_name, date) of the proof cache"""
    path = cache_db()
    if not os.path.exists(path):
        return []
    with sqlite3.connect(path) as db:
        try:
            if theory is None:
                return db.execute("SELECT * FROM isabelle_proof_cache_theories").fetchall()
            return db.execute("SELECT * FROM isabelle_proof_cache_theories WHERE theory_name = ?",
                              (theory,)).fetchall()
        except sqlite3.OperationalError:
            return []


def oracles(session_dir):
    """fact name -> list of oracle names, as written by the theory's ML block"""
    path = os.path.join(WORK, session_dir, "oracles.out")
    result = {}
    if os.path.exists(path):
        for line in open(path):
            m = re.match(r"(\S+): \[(.*)\]$", line.strip())
            if m:
                result[m.group(1)] = [s.strip() for s in m.group(2).split(",") if s.strip()]
        os.remove(path)  # no stale results for the next build
    return result


def undo_edit(path, old, new):
    edit(path, new, old)


def edit(path, old, new):
    path = os.path.join(WORK, path)
    text = open(path).read()
    assert old in text, (path, old)
    open(path, "w").write(text.replace(old, new, 1))


# assertions

FAILURES = []
CURRENT = [""]


def check(cond, msg, detail=""):
    if cond:
        print("PASS " + CURRENT[0] + ": " + msg)
    else:
        print("FAIL " + CURRENT[0] + ": " + msg)
        if detail:
            print("  " + detail.replace("\n", "\n  "))
        FAILURES.append(CURRENT[0] + ": " + msg)
    sys.stdout.flush()
    return cond


def check_ok(rc, out, what):
    tail = "\n".join(out.splitlines()[-25:])
    return check(rc == 0, what + " succeeds", tail)


def check_trusted(out, session, n, m):
    res = trusted(out, session)
    check(res == (n, m), "%s trusts %d/%d theories (got %s)" % (session, n, m, res))


def check_oracles(table, expect):
    for name, cached in expect.items():
        got = table.get(name)
        if cached:
            check(got == [CACHED], "%s carries only %s (got %s)" % (name, CACHED, got))
        else:
            check(got == [], "%s carries no oracle (got %s)" % (name, got))


def check_fast(session, reference):
    t, r = TIMING.get(session), TIMING.get(reference)
    check(t is not None and r is not None and t < FAST_FACTOR * r,
          "%s (%s s) much faster than %s (%s s)" % (session, t, reference, r))


def check_slow(session, reference):
    t, r = TIMING.get(session), TIMING.get(reference)
    check(t is not None and r is not None and t > SLOW_FACTOR * r,
          "%s (%s s) checks proofs like %s (%s s)" % (session, t, reference, r))


# cases

CASES = []
SLOW = set()  # cases run only with --slow (or when named)


def case(f):
    CASES.append(f)
    return f


def slow_case(f):
    SLOW.add(f.__name__)
    return case(f)


@case
def case_hol_uptodate():
    rc, out = isabelle("build", "-n", "-v", "HOL")
    check(rc == 0 and not re.search(r"^(Building|Running) ", out, re.M),
          "build -n -v HOL has nothing to rebuild", out)
    rc, out = isabelle("build", "-o", "proof_cache=false", "-n", "-v", "HOL")
    check(rc == 0 and not re.search(r"^(Building|Running) ", out, re.M),
          "build -o proof_cache=false -n -v HOL has nothing to rebuild (not a content option)",
          out)


@case
def case_plain_sessions():
    rows0 = len(cache_rows("MPT_C.Y"))
    rc, out = build("-b", "MPT_C")  # with heap: a later rebuild would use the cache
    check_ok(rc, out, "MPT_C")
    check_trusted(out, "MPT_C", 0, 1)
    check(len(cache_rows("MPT_C.Y")) == rows0 + 1, "MPT_C.Y certified (one new cache row)")

    rc, out = build("MPT_S")
    check_ok(rc, out, "MPT_S (sessions MPT_C)")
    check_trusted(out, "MPT_S", 1, 2)
    check_fast("MPT_S", "MPT_C")
    check_oracles(oracles("S"), {"t": True, "t2": False, "fy_pos": True, "slow_y1": True})

    rows = len(cache_rows())
    rc, out = build("-c", "-o", "proof_cache=false", "MPT_S")
    check_ok(rc, out, "MPT_S with proof_cache=false")
    check(trusted(out, "MPT_S") is None, "proof_cache=false: no proof cache lookup")
    check_slow("MPT_S", "MPT_C")
    check_oracles(oracles("S"), {"t": False, "t2": False, "fy_pos": False, "slow_y1": False})
    check(len(cache_rows()) == rows, "proof_cache=false: no cache writes")


@case
def case_merge():
    rc, out = build("-b", "MPT_D")
    check_ok(rc, out, "MPT_D = MPT_B + MPT_C")
    i_c = line_index(out, r"^Finished MPT_C ")
    i_merge = line_index(out, r"^(Building|Running) MPT_B\+MPT_C ")
    i_d = line_index(out, r"^(Building|Running) MPT_D ")
    check(i_merge >= 0 and i_merge < i_d and (i_c < 0 or i_c < i_merge),
          "build order: MPT_C before merge MPT_B+MPT_C before MPT_D", out)
    check_trusted(out, "MPT_B+MPT_C", 1, 1)
    check_fast("MPT_B+MPT_C", "MPT_C")
    check_oracles(oracles("D"),
      {"both": True, "only_x": False, "fx_pos": False, "fy_pos": True, "slow_y1": True})

    rc, out = build("MPT_D2")
    check_ok(rc, out, "MPT_D2 = MPT_B + MPT_C")
    check(not started(out, "MPT_B+MPT_C"), "MPT_D2 reuses merge MPT_B+MPT_C")


@case
def case_parent_failure():
    rows = len(cache_rows("MPT_BAD.Good0")) + len(cache_rows("MPT_BAD.Bad"))
    rc, out = build("MPT_FC")
    check(rc != 0, "MPT_FC = MPT_B + MPT_BAD fails")
    check(re.search(r"^MPT_BAD FAILED", out, re.M) is not None, "MPT_BAD fails", out)
    check(not started(out, "MPT_B+MPT_BAD") and not started(out, "MPT_FC"),
          "merge MPT_B+MPT_BAD and MPT_FC are cancelled", out)
    check(len(cache_rows("MPT_BAD.Good0")) + len(cache_rows("MPT_BAD.Bad")) == rows,
          "failed build: no cache writes (not even for its good theory)")


@case
def case_three_parents():
    rc, out = build("-b", "MPT_F")
    check_ok(rc, out, "MPT_F = MPT_B + MPT_C + MPT_E")
    check(not started(out, "MPT_B+MPT_C"), "MPT_F reuses merge MPT_B+MPT_C")
    check_trusted(out, "MPT_B+MPT_C+MPT_E", 1, 1)
    check_oracles(oracles("F"), {"v": True, "fx_pos": False, "fy_pos": True, "fw_pos": True})


@case
def case_diamond():
    rc, out = build("MPT_K")
    check_ok(rc, out, "MPT_K = MPT_D + MPT_F (diamond over MPT_B, MPT_C)")
    check_trusted(out, "MPT_D+MPT_F", 2, 2)
    check_oracles(oracles("K"),
      {"k": True, "v": True, "only_x": False, "fx_pos": False, "fy_pos": True, "fw_pos": True})

    rc, out = build("MPT_G")
    check_ok(rc, out, "MPT_G = MPT_D + MPT_B")
    check(not re.search(r"MPT_D\+MPT_B", out), "MPT_G: no merge (MPT_B contained in MPT_D)")


@case
def case_edit_miss():
    edit("C/Y.thy", "lemma fy_ge:", "lemma fy_ge': \"fy n \\<ge> 0\" by simp\n\nlemma fy_ge:")
    rows0 = len(cache_rows("MPT_C.Y"))
    rc, out = build("MPT_C")
    check_ok(rc, out, "MPT_C after editing Y")
    check_trusted(out, "MPT_C", 0, 1)
    check(len(cache_rows("MPT_C.Y")) == rows0 + 1, "edited MPT_C.Y certified under a new key")
    rc, out = build("MPT_S")
    check_ok(rc, out, "MPT_S after editing Y")
    check_trusted(out, "MPT_S", 1, 2)
    rc, out = build("MPT_D")
    check_ok(rc, out, "MPT_D after editing Y")
    check(not started(out, "MPT_C"),
          "MPT_C (built without heap) is not rebuilt for its heap: the merge does not load it")
    check_trusted(out, "MPT_B+MPT_C", 1, 1)


@case
def case_no_write():
    def rows():
        return cache_rows("MPT_W.G0")

    # -c: without build_thorough, changed options alone do not trigger a rebuild
    rows0 = rows()
    for opt in ["skip_proofs", "quick_and_dirty"]:
        rc, out = build("-c", "-o", opt, "MPT_W")
        check_ok(rc, out, "MPT_W with " + opt)
        check(rows() == rows0, opt + ": no cache writes")

    rc, out = build("-c", "MPT_W")
    check_ok(rc, out, "MPT_W")
    check_trusted(out, "MPT_W", 0, 1)
    rows1 = rows()
    check(len(rows1) == len(rows0) + 1, "MPT_W.G0 certified")

    rc, out = build("-c", "MPT_W")
    check_ok(rc, out, "MPT_W clean rebuild")
    check_trusted(out, "MPT_W", 1, 1)
    check(rows() == rows1, "trusted theory: not re-certified (rows and dates unchanged)")


@case
def case_proof_cache_false_merge():
    rows = len(cache_rows())
    rc, out = build("-c", "-o", "proof_cache=false", "MPT_B+MPT_C")
    check_ok(rc, out, "merge MPT_B+MPT_C with proof_cache=false")
    check(trusted(out, "MPT_B+MPT_C") is None, "proof_cache=false: no proof cache lookup")
    check_slow("MPT_B+MPT_C", "MPT_C")
    check(len(cache_rows()) == rows, "proof_cache=false: no cache writes")
    rc, out = build("MPT_D")
    check_ok(rc, out, "MPT_D afterwards")


# tester cases (T1-T7)

def check_oracle_lists(table, expect):
    """exact oracle lists (sorted) per fact"""
    for name, want in expect.items():
        got = table.get(name)
        check(got is not None and sorted(got) == sorted(want),
              "%s carries %s (got %s)" % (name, want, got))


@case
def case_parallel():
    rc, out = build("MPT_C")  # MPT_C.Y certified (no-op after plain_sessions)
    check_ok(rc, out, "MPT_C")
    rc, out = build("MPT_PAR")
    check_ok(rc, out, "MPT_PAR (sessions MPT_C: trusted Y next to new N, N2)")
    check_trusted(out, "MPT_PAR", 1, 4)
    check_oracle_lists(oracles("Par"), {
        "N.n1": [], "N.n2": [],  # loaded in parallel with the trusted Y: flag must not leak
        "N2.n2_own": [],  # child of the trusted Y, itself untrusted
        "N2.n2_y": [CACHED], "Y.fy_pos": [CACHED]})


@case
def case_loaded_files():
    def rows(thy):
        return len(cache_rows("MPT_L." + thy))
    n1, n2 = rows("L1"), rows("L2")
    rc, out = build("MPT_L")
    check_ok(rc, out, "MPT_L")
    check_trusted(out, "MPT_L", 0, 2)
    check(rows("L1") == n1 + 1 and rows("L2") == n2 + 1, "L1, L2 certified")
    for (path, thy, other, old, new) in [
            ("L/l1.ML", "L1", "L2", "val l1_value_ml = 1;", "val l1_value_ml = 2;"),
            ("L/l2.txt", "L2", "L1", "external data", "External data")]:
        n, n_other = rows(thy), rows(other)
        edit(path, old, new)
        rc, out = build("MPT_L")
        check_ok(rc, out, "MPT_L after editing only " + path)
        check_trusted(out, "MPT_L", 1, 2)
        check(rows(thy) == n + 1 and rows(other) == n_other,
              thy + " misses and is re-certified, " + other + " hits")
        undo_edit(path, old, new)
        rc, out = build("MPT_L")
        check_ok(rc, out, "MPT_L after reverting " + path)
        check_trusted(out, "MPT_L", 2, 2)
        check(rows(thy) == n + 1, thy + ": the old key hits again (no new row)")


@case
def case_import_change():
    def rows(thy):
        return len(cache_rows(thy))
    n = rows("MPT_IC.IB1")
    rc, out = build("MPT_IC")
    check_ok(rc, out, "MPT_IC = MPT_IP + IB0 IB1")
    check_trusted(out, "MPT_IP", 0, 1)
    check_trusted(out, "MPT_IC", 0, 2)
    rc, out = build("-c", "MPT_IC")
    check_ok(rc, out, "MPT_IC clean rebuild")
    check_trusted(out, "MPT_IC", 2, 2)

    edit0 = ("IC/IB0.thy", "lemma ib0:", "lemma ib0': \"ia \\<ge> 0\" by simp\n\nlemma ib0:")
    edit(*edit0)
    rc, out = build("MPT_IC")
    check_ok(rc, out, "MPT_IC after editing IB0 (import of IB1)")
    check_trusted(out, "MPT_IC", 0, 2)
    check(rows("MPT_IC.IB1") == n + 2, "unchanged IB1 misses through its import, re-certified")

    edita = ("IP/IA.thy", "lemma ia_pos:", "lemma ia_ge: \"ia \\<ge> 0\" by simp\n\nlemma ia_pos:")
    edit(*edita)
    rc, out = build("MPT_IC")
    check_ok(rc, out, "MPT_IC after editing IA in the parent session")
    check_trusted(out, "MPT_IP", 0, 1)
    check_trusted(out, "MPT_IC", 0, 2)
    check(rows("MPT_IC.IB1") == n + 3, "heap-chain import change: IB1 misses, re-certified")

    undo_edit(*edita)
    rc, out = build("MPT_IC")
    check_ok(rc, out, "MPT_IC after reverting IA")
    check_trusted(out, "MPT_IP", 1, 1)
    check_trusted(out, "MPT_IC", 2, 2)
    undo_edit(*edit0)


@case
def case_options():
    def rows():
        return len(cache_rows("MPT_W.G0"))
    rc, out = build("MPT_W")
    check_ok(rc, out, "MPT_W")
    rc, out = build("-c", "MPT_W")
    check_ok(rc, out, "MPT_W clean rebuild")
    check_trusted(out, "MPT_W", 1, 1)
    rows0 = rows()
    rc, out = build("-c", "-o", "ML_print_depth=7", "MPT_W")
    check_ok(rc, out, "MPT_W with content option ML_print_depth=7")
    check_trusted(out, "MPT_W", 0, 1)
    check(rows() == rows0 + 1, "changed content option: miss, certified under a new key")
    rc, out = build("-c", "-o", "ML_print_depth=7", "MPT_W")
    check_ok(rc, out, "MPT_W with ML_print_depth=7 again")
    check_trusted(out, "MPT_W", 1, 1)
    rc, out = build("-c", "-o", "timeout_scale=2", "MPT_W")
    check_ok(rc, out, "MPT_W with non-content option timeout_scale=2")
    check_trusted(out, "MPT_W", 1, 1)


@case
def case_skip_oracle():
    def rows(thy):
        return len(cache_rows("MPT_Q." + thy))
    n2, nc = rows("Q2"), rows("QChk")
    rc, out = build("MPT_Q")
    check_ok(rc, out, "MPT_Q")
    check_trusted(out, "MPT_Q", 0, 3)
    check(rows("Q1") == 0, "sorry under a theory-local quick_and_dirty: Q1 never certified")
    check(rows("Q2") == n2 + 1, "tool-like Skip_Proof.make_thm in Q2: certified")
    check(rows("QChk") == nc + 1, "QChk certified")
    real = oracles("Q")
    check_oracle_lists(real, {"Q1.q1": ["Pure.skip_proof"], "Q1.q1_real": [],
                              "Q2.q2_raw": ["Pure.skip_proof"], "Q2.q2": ["Pure.skip_proof"],
                              "Q2.q2_real": []})
    rc, out = build("-c", "MPT_Q")
    check_ok(rc, out, "MPT_Q clean rebuild")
    check_trusted(out, "MPT_Q", 2, 3)
    cached = oracles("Q")
    check_oracle_lists(cached, {"Q1.q1": ["Pure.skip_proof"], "Q1.q1_real": [],
                                "Q2.q2_raw": ["Pure.skip_proof"], "Q2.q2_real": [CACHED]})
    # documented limit: the oracle trail stops at a cached proof (skip_proof not shown)
    check_oracle_lists(cached, {"Q2.q2": [CACHED]})


@case
def case_robustness():
    db = cache_db()
    backup = db + ".mp-tests-backup"
    shutil.copy2(db, backup)
    try:
        os.remove(db)
        rc, out = build("-c", "MPT_W")
        check_ok(rc, out, "MPT_W without proof_cache.db")
        check_trusted(out, "MPT_W", 0, 1)
        check(len(cache_rows("MPT_W.G0")) == 1, "database re-created, G0 certified")

        os.remove(db)
        os.mkdir(db)  # unusable database
        rc, out = build("-c", "MPT_W")
        check_ok(rc, out, "MPT_W with an unusable proof_cache.db")
        check(re.search(r"Proof cache MPT_W: ", out) is not None and
              re.search(r"^### Proof cache MPT_W", out, re.M) is not None,
              "lookup/write failures are warnings", out)
        os.rmdir(db)

        shutil.copy2(backup, db)
        os.chmod(db, 0o444)
        rc, out = build("-c", "MPT_W")
        check_ok(rc, out, "MPT_W with a read-only proof_cache.db (lookup)")
        check_trusted(out, "MPT_W", 1, 1)
        rc, out = build("-c", "-o", "ML_print_depth=11", "MPT_W")
        check_ok(rc, out, "MPT_W with a read-only proof_cache.db (write)")
        check(re.search(r"^### Proof cache MPT_W", out, re.M) is not None,
              "write to read-only database: warning", out)
    finally:
        if os.path.isdir(db):
            os.rmdir(db)
        elif os.path.exists(db):
            os.chmod(db, 0o644)
        shutil.move(backup, db)

    # concurrent writers (SQLite lock upgrade conflicts are retried): three rounds
    for rnd in range(3):
        for d in ["CA", "CB"]:
            path = os.path.join(WORK, d, d + ".thy")
            text = re.sub(r"nonce: \S+", "nonce: " + uuid.uuid4().hex, open(path).read())
            open(path, "w").write(text)
        n = {s: len(cache_rows(s + "." + s[len("MPT_"):])) for s in ["MPT_CA", "MPT_CB"]}
        procs = [subprocess.Popen([ISABELLE, *build_args(s)], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, env=tool_env())
                 for s in ["MPT_CA", "MPT_CB"]]
        for s, p in zip(["MPT_CA", "MPT_CB"], procs):
            out = p.communicate()[0]
            record_timing(out)
            check_ok(p.returncode, out, "%s (built concurrently, round %d)" % (s, rnd))
            check(len(cache_rows(s + "." + s[len("MPT_"):])) == n[s] + 1,
                  "%s certified (round %d)" % (s, rnd), out)


@slow_case
def case_fresh():
    rows0 = cache_rows("MPT_W.G0")
    rc, out = build("-f", "MPT_W")
    check_ok(rc, out, "MPT_W with -f (fresh build: Pure, HOL, MPT_W)")
    check(started(out, "HOL") is not None, "-f rebuilds the whole chain (stock)")
    for s in ["HOL", "MPT_W"]:
        res = trusted(out, s)
        check(res is not None and res[0] == 0, "-f: %s trusts nothing (got %s)" % (s, res))
    rows1 = cache_rows("MPT_W.G0")
    check(set(rows1) - set(rows0) != set(),
          "-f: still certifies (new row, or the existing row re-written with a new date)")
    rc, out = build("-c", "MPT_W")
    check_ok(rc, out, "MPT_W with -c")
    check_trusted(out, "MPT_W", 1, 1)


@case
def case_multiparent_corners():
    rc, out = build("MPT_MC")
    check_ok(rc, out, "MPT_MC = MPT_B + MPT_CC, condition group skipped (MPT_COND unset)")
    print("  " + "\n  ".join(l for l in out.splitlines()
                             if re.search(r"MPT_CC|MPT_B\+MPT_CC|[Ss]kipping", l)))
    rc, out = build("-c", "MPT_CC", env={"MPT_COND": "1"})
    check_ok(rc, out, "MPT_CC, MPT_MC with condition group (MPT_COND=1)")
    rc, out = build("MPT_MC", env={"MPT_COND": "1"})
    check_ok(rc, out, "MPT_MC with condition group (MPT_COND=1)")
    print("  " + "\n  ".join(l for l in out.splitlines() if "Proof cache" in l))
    check(len(cache_rows("MPT_CC.CC1")) == 0, "condition group: never certified")

    rc, out = build("MPT_MD")
    check_ok(rc, out, "MPT_MD = MPT_B + MPT_CD (CD with sessions + document_theories)")

    rc, out = build("MPT_O1", "MPT_O2")
    check_ok(rc, out, "MPT_O1 = MPT_B + MPT_C and MPT_O2 = MPT_C + MPT_B")
    check_trusted(out, "MPT_C+MPT_B", 1, 1)
    # the re-loaded side carries cached_proof; the heap side (MPT_B resp. MPT_C) depends on
    # how that heap was built (a rebuild from the cache is legitimate), so it is not checked
    check_oracles(oracles("O1"), {"fy_pos": True, "O1_both": True})
    check_oracles(oracles("O2"), {"fx_pos": True, "O2_both": True})
    thms = [open(os.path.join(WORK, d, "thms.out")).read() for d in ["O1", "O2"]]
    check(thms[0] == thms[1] and thms[0].strip() != "",
          "parent order: same theorems", "\n".join(thms))


# copied to work/afp-demo by setup(), with the nonce: Demo is new to the proof cache
AFP_DEMO = os.path.join(WORK, "afp-demo")
AFP_A, AFP_B = "Word_Lib", "Automatic_Refinement"
AFP_MERGE = AFP_A + "+" + AFP_B


def timings(out):
    """session -> (elapsed, cpu) of its Timing line (theory processing)"""
    return {m.group(1): (float(m.group(2)), float(m.group(3)))
            for m in re.finditer(
                r"^Timing (\S+) \(\d+ threads, ([\d.]+)s elapsed time, ([\d.]+)s cpu", out, re.M)}


@slow_case
def case_afp_demo():
    """AFP_Demo_Merge = Word_Lib + Automatic_Refinement vs. baseline with sessions"""
    def afp_build(*args):
        cmd = ["build", "-d", AFP_DEMO, "-v", *BUILD_OPTIONS, *args]
        print("  $ isabelle " + " ".join(cmd).replace(AFP_DEMO, "mp-tests/work/afp-demo"))
        sys.stdout.flush()
        rc, out = isabelle(*cmd)
        return rc, out

    table = []

    def row(label, out, session):
        t = timings(out).get(session)
        tr = trusted(out, session)
        m = re.search(r"^Finished " + re.escape(session) + r" \((\d+):(\d+):(\d+) elapsed", out, re.M)
        total = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None
        table.append((label, session, t, total, tr))

    # A stock (no cache: its facts carry no oracle), B with the cache (certifies B's theories)
    rc, out = afp_build("-c", "-b", "-o", "proof_cache=false", AFP_A, AFP_B)
    check_ok(rc, out, "parents %s, %s (clean build, proof_cache=false)" % (AFP_A, AFP_B))
    row("parent A, proof_cache=false", out, AFP_A)
    row("parent B, proof_cache=false", out, AFP_B)
    rc, out = afp_build("-c", AFP_B)
    check_ok(rc, out, "parent %s with the cache" % AFP_B)
    row("parent B, cache", out, AFP_B)

    rc, out = afp_build("AFP_Demo_Merge")
    check_ok(rc, out, "AFP_Demo_Merge")
    row("merge, cache", out, AFP_MERGE)
    row("child, cache", out, "AFP_Demo_Merge")
    res = trusted(out, AFP_MERGE)
    check(res is not None and res[0] == res[1] and res[1] > 0,
          "merge %s trusts all re-loaded theories (got %s)" % (AFP_MERGE, res))
    ora = oracles(os.path.join(AFP_DEMO, "Merge"))
    check_oracle_lists(ora, {"demo": [CACHED], "demo_rel": [CACHED],
                             "list_rel_id_simp": [CACHED], "fun_relI": [CACHED],
                             "demo_word": [], "word_le_minus_one_leq": []})

    rc, out = afp_build("-c", "-o", "proof_cache=false", AFP_MERGE, "AFP_Demo_Merge")
    check_ok(rc, out, "AFP_Demo_Merge with proof_cache=false")
    row("merge, proof_cache=false", out, AFP_MERGE)
    row("child, proof_cache=false", out, "AFP_Demo_Merge")
    ora = oracles(os.path.join(AFP_DEMO, "Merge"))
    check_oracle_lists(ora, {"demo": [], "demo_rel": [], "list_rel_id_simp": [],
                             "demo_word": []})

    rc, out = afp_build("-c", "AFP_Demo_Base")
    check_ok(rc, out, "AFP_Demo_Base (sessions Automatic_Refinement), cache")
    row("baseline, cache", out, "AFP_Demo_Base")
    rc, out = afp_build("-c", "-o", "proof_cache=false", "AFP_Demo_Base")
    check_ok(rc, out, "AFP_Demo_Base, proof_cache=false")
    row("baseline, proof_cache=false", out, "AFP_Demo_Base")

    rc, out = afp_build("-c", AFP_MERGE, "AFP_Demo_Merge")  # leave cached heaps behind
    check_ok(rc, out, "AFP_Demo_Merge rebuilt with cache")

    print("\n| build | session | theories elapsed / cpu | session total | trusted |\n"
          "|---|---|---|---|---|")
    for label, session, t, total, tr in table:
        print("| %s | `%s` | %s | %s | %s |" % (
            label, session, "%.1f s / %.1f s" % t if t else "-",
            "%d s" % total if total is not None else "-", "%d/%d" % tr if tr else "-"))
    print()


# main

def copy_tree(src, dst, nonce):
    for root, _, files in os.walk(src):
        target = os.path.join(dst, os.path.relpath(root, src))
        os.makedirs(target, exist_ok=True)
        for name in files:
            if name.endswith(".out"):
                continue
            text = open(os.path.join(root, name)).read()
            open(os.path.join(target, name), "w").write(text.replace("@NONCE@", nonce))


def setup():
    shutil.rmtree(WORK, ignore_errors=True)
    nonce = uuid.uuid4().hex
    copy_tree(SRC, WORK, nonce)
    copy_tree(os.path.join(HERE, "afp-demo"), AFP_DEMO, nonce)


def main(args):
    global ISABELLE
    names = {f.__name__[len("case_"):]: f for f in CASES}
    if "--isabelle" in args:
        i = args.index("--isabelle")
        if i + 1 >= len(args):
            print("Missing argument for --isabelle")
            return 2
        ISABELLE = os.path.abspath(args[i + 1])
        args = args[:i] + args[i + 2:]
    if args[:1] == ["-l"]:
        print("\n".join(n + (" (--slow)" if f.__name__ in SLOW else "") for n, f in names.items()))
        return 0
    slow = "--slow" in args
    args = [a for a in args if a != "--slow"]
    unknown = [a for a in args if a not in names]
    if unknown:
        print("Unknown case(s): " + ", ".join(unknown) + "\nCases: " + ", ".join(names))
        return 2
    if not os.access(ISABELLE, os.X_OK):
        print("Isabelle tool not executable: " + ISABELLE)
        return 2
    print("Isabelle tool: %s (ISABELLE_HOME=%s, ISABELLE_HOME_USER=%s)" % (
        ISABELLE, getenv("ISABELLE_HOME"), getenv("ISABELLE_HOME_USER")))
    setup()
    for f in CASES:
        name = f.__name__[len("case_"):]
        if args and name not in args:
            continue
        if not args and f.__name__ in SLOW and not slow:
            continue
        CURRENT[0] = name
        print("=== " + name)
        sys.stdout.flush()
        try:
            f()
        except Exception as exn:
            check(False, "exception " + repr(exn))
    print()
    if FAILURES:
        print("%d FAILED:\n  %s" % (len(FAILURES), "\n  ".join(FAILURES)))
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
