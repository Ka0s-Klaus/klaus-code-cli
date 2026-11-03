import subprocess
import sys


def pytest(*args):
    proc = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


code, out = pytest("-q", "--strict-markers")
if code != 0:
    sys.exit(f"pytest por defecto falla (¿recoge scripts/ o el marcador no está registrado?):\n{out}")
if "1 passed" not in out or "1 deselected" not in out:
    sys.exit(f"Por defecto debe pasar 1 test y deseleccionar el slow:\n{out}")
code, out = pytest("-q", "--strict-markers", "-m", "slow")
if code != 0 or "1 passed" not in out:
    sys.exit(f"-m slow debe ejecutar exactamente el test slow:\n{out}")
code, out = pytest("--markers")
if "@pytest.mark.slow:" not in out:
    sys.exit("El marcador slow no está registrado con descripción")
print("Configuración correcta")
