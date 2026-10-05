# check_insert.py
from pathlib import Path
from core.tools import insert_at_cursor

f = Path("check_insert_demo.py")
f.write_text("def add(a, b):\n    result = \n    return result\n", encoding="utf-8")

print("改前:")
print(f.read_text(encoding="utf-8"))

print(insert_at_cursor(str(f), line=2, col=14, text="a + b"))

print("\n改后（磁盘上的真实内容）:")
print(f.read_text(encoding="utf-8"))