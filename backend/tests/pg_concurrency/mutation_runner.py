#!/usr/bin/env python3
"""Ejecuta la linea base y las mutaciones sobre COPIAS desechables de backend/.

No arranca ni detiene Docker: lo invoca infrastructure/test-db/pg_test_db.py con el
contenedor ya levantado y TEST_DATABASE_URL en el entorno. El repositorio nunca se
modifica: cada corrida usa una copia en un directorio temporal FUERA de la raiz completa
del repositorio (no solo de backend/), y la mutacion se aplica solo a esa copia. Si el
directorio temporal no cumple esa condicion, se aborta y se elimina.

Para cada mutacion se exige (ademas de que el ancla coincida y el codigo compile):
  1. que el codigo que realmente se importa sea el de la copia mutada;
  2. que cada prueba `must_fail` FALLE (no error ni skip) y que su mensaje contenga
     el codigo [CF-DETECT:<codigo>] esperado (razon esperada);
  3. que cada control positivo PASE;
  4. que no haya otros fallos entre las pruebas seleccionadas.
Si la linea base no pasa completa, no se ejecuta ninguna mutacion.
"""
import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mutations import MUTATIONS, SELECTION_K, TARGET, MutationError, apply_edits  # noqa: E402

IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".venv", "venv", ".env", ".env.*", "*.db", "node_modules"
)


def log(message):
    print(f"[mutation-runner] {message}", flush=True)


def parse_junit(path):
    results = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        name = case.get("name")
        status, text = "passed", ""
        for tag in ("failure", "error", "skipped"):
            node = case.find(tag)
            if node is not None:
                status = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                text = (node.get("message") or "") + "\n" + (node.text or "")
                break
        results[name] = (status, text)
    return results


def is_inside(path: Path, root: Path) -> bool:
    """True si `path` es `root` o esta dentro de el (ambos resueltos, sin enlaces simbolicos)."""
    return path.resolve().is_relative_to(root.resolve())


def make_copy(backend_dir: Path, repo_root: Path, workroot: Path, name: str) -> Path:
    destination = workroot / name / "backend"
    destination.parent.mkdir(parents=True)
    if is_inside(destination, repo_root):
        raise RuntimeError("la copia quedaria dentro del repositorio; no se copia")
    shutil.copytree(backend_dir, destination, ignore=IGNORE)
    return destination


def verify_import_origin(copy_backend: Path, env) -> None:
    """Asegura que `import app` resuelve a la COPIA (y no a un backend instalado en el venv)."""
    code = "import app.routers.shipments as m; print(m.__file__)"
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=copy_backend, env=env, capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"no se pudo importar app desde la copia: {proc.stderr.strip()[-300:]}")
    origin = Path(proc.stdout.strip()).resolve()
    if not origin.is_relative_to(copy_backend.resolve()):
        raise RuntimeError(f"`app` se importa desde {origin}, no desde la copia mutada")


def run_pytest(copy_backend: Path, junit: Path, token_file: str, env, timeout: int, k_expr=None):
    cmd = [
        sys.executable, "-m", "pytest", "tests/pg_concurrency",
        "-m", "pg_concurrency", "-p", "no:cacheprovider", "-q",
        f"--pg-token-file={token_file}", f"--junitxml={junit}",
    ]
    if k_expr:
        cmd += ["-k", k_expr]
    try:
        proc = subprocess.run(cmd, cwd=copy_backend, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, {}
    results = parse_junit(junit) if junit.exists() else {}
    return proc.returncode, results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-dir", required=True)
    parser.add_argument("--repo-root", default=None, help="raiz del repositorio (por defecto, el padre de --backend-dir)")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--only", nargs="*", default=[], help="ids de mutacion (p. ej. M2 M3)")
    parser.add_argument("--timeout", type=int, default=900, help="segundos por corrida de pytest")
    args = parser.parse_args()

    backend_dir = Path(args.backend_dir).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else backend_dir.parent
    if not is_inside(backend_dir, repo_root):
        log("--backend-dir no esta dentro de --repo-root; se aborta")
        return 2
    if not os.environ.get("TEST_DATABASE_URL"):
        log("TEST_DATABASE_URL no esta definida: este runner solo se invoca desde pg_test_db.py")
        return 2
    selected = [m for m in MUTATIONS if not args.only or m.id in args.only]
    unknown = set(args.only) - {m.id for m in MUTATIONS}
    if unknown:
        log(f"mutaciones desconocidas: {sorted(unknown)}")
        return 2

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    workroot = Path(tempfile.mkdtemp(prefix="cf-mut-"))
    report = {"baseline": None, "mutations": {}}
    exit_code = 0
    try:
        # El directorio temporal debe quedar fuera de la RAIZ COMPLETA del repositorio (no solo de
        # backend/). Si no es asi se aborta; el `finally` de abajo lo elimina en cualquier caso.
        if is_inside(workroot, repo_root):
            log("el directorio temporal quedo dentro de la raiz del repositorio; se aborta y se limpia")
            return 2
        # ---- linea base (copia sin mutar, suite completa incluida la de carrera) ----
        base_copy = make_copy(backend_dir, repo_root, workroot, "baseline")
        verify_import_origin(base_copy, env)
        rc, base = run_pytest(base_copy, workroot / "baseline.xml", args.token_file, env, args.timeout)
        bad = {n: s for n, (s, _t) in base.items() if s != "passed"}
        if rc != 0 or not base or bad:
            log(f"LINEA BASE FALLIDA (rc={rc}, no-pasan={bad or 'sin resultados/timeout'}): no se ejecutan mutaciones")
            report["baseline"] = {"ok": False, "not_passed": bad}
            print(json.dumps(report, indent=2))
            return 1
        log(f"linea base OK: {len(base)} pruebas pasan")
        report["baseline"] = {"ok": True, "tests": len(base)}

        # ---- mutaciones ----
        for mutation in selected:
            log(f"=== {mutation.id}: {mutation.title}")
            missing = [t for t in mutation.requires_baseline if base.get(t, ("", ""))[0] != "passed"]
            if missing:
                log(f"{mutation.id}: precondicion de linea base no cumplida ({missing}); se omite")
                report["mutations"][mutation.id] = {"ok": False, "reason": f"precondicion {missing}"}
                exit_code = 1
                continue

            copy = make_copy(backend_dir, repo_root, workroot, mutation.id)
            target = copy / TARGET
            original = target.read_text(encoding="utf-8")
            try:
                mutated = apply_edits(original, mutation)
                compile(mutated, str(target), "exec")
            except (MutationError, SyntaxError) as exc:
                log(f"{mutation.id}: {exc}")
                report["mutations"][mutation.id] = {"ok": False, "reason": str(exc)}
                exit_code = 1
                continue
            target.write_text(mutated, encoding="utf-8")
            if hashlib.sha256(original.encode()).digest() == hashlib.sha256(mutated.encode()).digest():
                raise RuntimeError(f"{mutation.id}: la mutacion no cambio el archivo")
            for line in difflib.unified_diff(
                original.splitlines(), mutated.splitlines(), f"a/{TARGET}", f"b/{TARGET}", lineterm="", n=1
            ):
                print("    " + line)
            verify_import_origin(copy, env)

            rc, results = run_pytest(
                copy, workroot / f"{mutation.id}.xml", args.token_file, env, args.timeout, SELECTION_K
            )
            if rc is None:
                log(f"{mutation.id}: TIMEOUT -> corrida inconclusa (se revisaran sesiones vivas en el teardown)")
                report["mutations"][mutation.id] = {"ok": False, "reason": "timeout"}
                exit_code = 1
                continue

            problems = []
            for test, code in mutation.must_fail.items():
                status, text = results.get(test, ("ausente", ""))
                marker = f"[CF-DETECT:{code}]"
                if status != "failed":
                    problems.append(f"{test}: debia FALLAR y resulto '{status}'")
                elif marker not in text:
                    problems.append(f"{test}: fallo, pero sin la razon esperada {marker}")
            for test in mutation.must_pass:
                status = results.get(test, ("ausente", ""))[0]
                if status != "passed":
                    problems.append(f"control {test}: debia PASAR y resulto '{status}'")
            accounted = set(mutation.must_fail) | set(mutation.must_pass)
            for test, (status, _t) in results.items():
                if test not in accounted and status in ("failed", "error"):
                    problems.append(f"{test}: fallo no previsto en la matriz ({status})")

            ok = not problems
            report["mutations"][mutation.id] = {"ok": ok, "problems": problems}
            if ok:
                detected = ", ".join(f"{t} [{c}]" for t, c in mutation.must_fail.items())
                log(f"{mutation.id}: DETECTADA -> {detected}; {len(mutation.must_pass)} controles pasan")
            else:
                exit_code = 1
                for problem in problems:
                    log(f"{mutation.id}: PROBLEMA -> {problem}")
    finally:
        shutil.rmtree(workroot, ignore_errors=True)

    print(json.dumps(report, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
