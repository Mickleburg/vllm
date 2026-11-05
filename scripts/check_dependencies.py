"""Fail the image build if any installed Python distribution differs from the lock."""
import importlib.metadata
import re
import sys
from pathlib import Path


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


expected = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line or line.startswith("#"):
        continue
    name, version = line.split("==", 1)
    expected[normalize(name)] = version
actual = {normalize(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()}
if actual != expected:
    raise SystemExit(f"Dependency lock mismatch: {sorted(set(actual.items()) ^ set(expected.items()))}")
print(f"Verified {len(expected)} pinned Python distributions")
