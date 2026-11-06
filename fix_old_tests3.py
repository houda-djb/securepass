"""One-off: cancelling now asks for a reason and the password, so old tests must send them."""
import re
from pathlib import Path

DATA = '{"reason": "plans", "password": "Correct-horse-42"}'
changed = 0
for path in sorted(Path("tests").glob("test_*.py")):
    if path.name == "test_phase26.py":
        continue
    text = path.read_text(encoding="utf-8")
    fixed = re.sub(r'(\.post\([^\n]*?/cancel")\)', lambda m: m.group(1) + ", data=" + DATA + ")", text)
    fixed = re.sub(r'(\.post\([^\n]*?/cancel"), data=\{"csrf_token": ([a-z_]+)\}\)',
                   lambda m: m.group(1) + ', data={"csrf_token": ' + m.group(2)
                   + ', "reason": "plans", "password": "Correct-horse-42"})', fixed)
    if fixed != text:
        path.write_text(fixed, encoding="utf-8", newline="")
        print("updated", path)
        changed += 1
print(changed, "file(s) updated")
