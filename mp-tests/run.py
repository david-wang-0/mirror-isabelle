#!/usr/bin/env python3
"""Test suite for multi-parent sessions and the proof cache (see MP-README.md).

Usage: mp-tests/run.sh [-l] [CASE ...]

Copies src/ to work/ (git-ignored), substituting a fresh @NONCE@ so that the
theories carrying it are new to the proof cache, then runs the cases in CASES
order (all, or the given ones) with bin/isabelle-mp on the normal user heaps.
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
ISABELLE = os.path.join(ISABELLE_HOME, "bin", "isabelle-mp")
SRC = os.path.join(HERE, "src")
WORK = os.path.join(HERE, "work")

BUILD_OPTIONS = ["-o", "threads=8"]

# a cached/merged session must take less than this fraction of the real check
FAST_FACTOR = 0.25
# a session checked in full must take more than this fraction of the real check
SLOW_FACTOR = 0.5

CACHED = "Pure.cached_proof"


# utilities

def isabelle(*args):
    proc = subprocess.run([ISABELLE, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)
    return proc.returncode, proc.stdout


def getenv(name):
    return isabelle("getenv", "-b", name)[1].strip()


TIMING = {}  # session -> maximal elapsed seconds of its builds (a real check, not a cached one)


def build(*args):
    """isabelle build -d work -v ARGS: (rc, output); records Timing lines"""
    rc, out = isabelle("build", "-d", WORK, "-v", *BUILD_OPTIONS, *args)
    for m in re.finditer(r"^Timing (\S+) \(\d+ threads, ([\d.]+)s elapsed", out, re.M):
        TIMING[m.group(1)] = max(TIMING.get(m.group(1), 0.0), float(m.group(2)))
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


def case(f):
    CASES.append(f)
    return f


@case
def case_hol_uptodate():
    rc, out = isabelle("build", "-n", "-v", "HOL")
    check(rc == 0 and not re.search(r"^(Building|Running) ", out, re.M),
          "build -n -v HOL has nothing to rebuild", out)


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


# main

def setup():
    shutil.rmtree(WORK, ignore_errors=True)
    nonce = uuid.uuid4().hex
    for root, _, files in os.walk(SRC):
        target = os.path.join(WORK, os.path.relpath(root, SRC))
        os.makedirs(target, exist_ok=True)
        for name in files:
            text = open(os.path.join(root, name)).read()
            open(os.path.join(target, name), "w").write(text.replace("@NONCE@", nonce))


def main(args):
    names = {f.__name__[len("case_"):]: f for f in CASES}
    if args[:1] == ["-l"]:
        print("\n".join(names))
        return 0
    unknown = [a for a in args if a not in names]
    if unknown:
        print("Unknown case(s): " + ", ".join(unknown) + "\nCases: " + ", ".join(names))
        return 2
    setup()
    for f in CASES:
        name = f.__name__[len("case_"):]
        if args and name not in args:
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
