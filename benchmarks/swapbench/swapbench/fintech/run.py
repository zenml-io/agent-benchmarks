"""tau2 CLI with the fintech domain registered:  python -m swapbench.fintech.run run -d fintech ...
(set SWAPBENCH_FINTECH_DIR to the generated data dir; needs the tau2 venv). With SWAPBENCH_GENMOCK=<mock.py>
and SWAPBENCH_GENMOCK_DOMAIN=fintech|retail it also registers <domain>_gen (see swapbench/genmock.py)."""
import os
import sys

from swapbench.fintech.domain import register

register()
if os.environ.get("SWAPBENCH_GENMOCK"):  # a trace-inferred mock as <domain>_gen
    from swapbench.genmock import register as register_gen
    register_gen(os.environ.get("SWAPBENCH_GENMOCK_DOMAIN", "fintech"), os.environ["SWAPBENCH_GENMOCK"])

if os.environ.get("SWAPBENCH_JEV") == "1":  # agent `jev_gate`: writes checked by Jev (see swapbench/jev_agent.py)
    from swapbench.jev_agent import register as register_jev
    register_jev()

if os.environ.get("SWAPBENCH_HYBRID") == "1":  # agents `jev_route` and `split` (see swapbench/hybrid_agent.py)
    from swapbench.hybrid_agent import register as register_hybrid
    register_hybrid()

from tau2.cli import main  # noqa: E402  (after registration so the CLI lists the domain)

if __name__ == "__main__":
    sys.exit(main())
