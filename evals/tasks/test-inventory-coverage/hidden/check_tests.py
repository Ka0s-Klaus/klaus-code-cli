import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ORIGINAL = Path("inventory.py").read_text()
MUTANTS = {
    "sin validar qty en remove": ('        if qty <= 0:\n            raise ValueError("qty debe ser > 0")\n        current',
                                  "        current"),
    "retirar todo el stock falla": ("if qty > current:", "if qty >= current:"),
    "permite stock negativo": ('if qty > current:\n            raise ValueError("stock insuficiente")',
                               "if False:\n            pass"),
}


def run_tests(source):
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(".", tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
        (Path(tmp) / "inventory.py").write_text(source)
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=tmp,
                              capture_output=True).returncode


if run_tests(ORIGINAL) != 0:
    sys.exit("Los tests fallan con la implementación correcta")
survivors = []
for name, (old, new) in MUTANTS.items():
    assert old in ORIGINAL, name
    if run_tests(ORIGINAL.replace(old, new, 1)) == 0:
        survivors.append(name)
if survivors:
    sys.exit(f"Mutantes no detectados por los tests: {survivors}")
print("Todos los mutantes detectados")
