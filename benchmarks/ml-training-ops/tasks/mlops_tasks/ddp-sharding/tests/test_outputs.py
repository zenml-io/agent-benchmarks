import json, os, shutil, subprocess

APP = os.environ.get("APP_DIR", "/app")


def test_each_sample_once_per_epoch():
    for r in (0, 1):
        p = os.path.join(APP, f"seen_rank{r}.json")
        if os.path.exists(p):
            os.remove(p)
    torchrun = shutil.which("torchrun")
    subprocess.run([torchrun, "--nproc_per_node", "2", os.path.join(APP, "train_ddp.py")], cwd=APP,
                   check=True, timeout=600, env={**os.environ, "OMP_NUM_THREADS": "1"})
    r0 = json.load(open(os.path.join(APP, "seen_rank0.json")))
    r1 = json.load(open(os.path.join(APP, "seen_rank1.json")))
    assert len(r0) == len(r1) == 3
    for e in range(3):
        a, b = r0[e], r1[e]
        assert not set(a) & set(b), "ranks overlap"
        assert sorted(a + b) == list(range(4096)), "not every sample exactly once"
    assert r0[0] != r0[1], "order does not change between epochs"
