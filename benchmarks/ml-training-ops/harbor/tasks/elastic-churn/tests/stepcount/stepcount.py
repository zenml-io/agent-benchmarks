"""Read the counts written by stepcount/sitecustomize.py."""
import collections
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def env(count_file, base=None):
    """Environment for a job whose optimizer steps and backward passes should be counted."""
    e = dict(base if base is not None else os.environ)
    e["PYTHONPATH"] = HERE + (os.pathsep + e["PYTHONPATH"] if e.get("PYTHONPATH") else "")
    e["STEPCOUNT_FILE"] = count_file
    return e


def counts(count_file):
    """{(rank, kind): n}. Fails if the instrumentation never loaded in the job."""
    c = collections.Counter()
    if os.path.exists(count_file):
        for line in open(count_file):
            parts = line.split()
            if len(parts) == 2:
                c[(parts[0], parts[1])] += 1
    assert c[("0", "start")], f"grader instrumentation did not load in the job ({count_file})"
    return c
