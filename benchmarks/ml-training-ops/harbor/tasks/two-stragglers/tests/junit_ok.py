"""Exit 0 only if the JUnit report shows at least one test, all of which passed (none failed,
errored or was skipped). Guards against a test process that exits 0 without running the tests."""
import sys
import xml.etree.ElementTree as ET

try:
    root = ET.parse(sys.argv[1]).getroot()
except (OSError, ET.ParseError, IndexError) as e:
    print(f"junit_ok: no usable report: {e}")
    sys.exit(1)
cases = list(root.iter("testcase"))
bad = [c.get("name") for c in cases if any(ch.tag in ("failure", "error", "skipped") for ch in c)]
if not cases or bad:
    print(f"junit_ok: {len(cases)} tests, not passed: {bad}")
    sys.exit(1)
print(f"junit_ok: {len(cases)} tests passed")
