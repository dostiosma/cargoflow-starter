#!/usr/bin/env python3
"""Ciclo de vida de un PostgreSQL DESECHABLE para las pruebas de concurrencia.

Subcomandos:
  check      Verificaciones previas sin efectos (docker presente, paquetes importables).
  suite      Tests unitarios de la guarda -> contenedor -> suite pg_concurrency -> teardown.
  mutations  Tests unitarios -> contenedor -> linea base + mutaciones M1-V/M1-D/M2/M3 -> teardown.
  list       Lista (solo lectura) los contenedores creados por este script.

Garantias (ver README.md):
  * Contenedor propio, publicado SOLO en 127.0.0.1 (puerto efimero), credenciales
    aleatorias, tmpfs, una base y un rol de privilegios minimos por ejecucion.
  * Sentinel con el sha256 de un token; el token vive en un archivo 0600 en un
    directorio privado FUERA del repo. Ningun secreto viaja por argv ni por logs.
  * Solo se admite un endpoint Docker LOCAL (socket Unix o TCP de loopback verificable): el
    laboratorio publica PostgreSQL en 127.0.0.1, accesible solo si el daemon esta en este
    mismo entorno. Los contextos SSH y TCP remotos se rechazan antes de crear nada.
  * El contexto/endpoint de Docker usado al crear el contenedor, junto con el ID del Docker
    Engine, se registra y se FIJA (`docker --context <ctx>`) en todas las operaciones
    posteriores, y el ID se verifica antes de cada consulta; si no se puede
    verificar o cambio (otro contexto activo, endpoint modificado, contexto borrado), el
    estado del contenedor se trata como DESCONOCIDO y se conserva todo. Con DOCKER_HOST
    definido solo se continua si se DEMUESTRA que el contexto capturado es ese destino
    (contexto 'default' y endpoint identico a DOCKER_HOST); si no, falla cerrado y no se
    crea el contenedor ni se aprovisiona nada.
  * El teardown solo destruye el contenedor que ESTE proceso creo (id + etiquetas
    verificados) y se niega si quedan sesiones activas, hay marcador de contaminacion
    o NO se puede verificar el estado del contenedor (un error al consultar Docker no
    equivale a "contenedor inexistente"): en esos casos conserva contenedor y
    directorio privado (credenciales) para recuperacion controlada, y no declara
    exitoso el teardown.
  * Solo biblioteca estandar. Usa `docker` mediante subprocess sin shell.
"""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import os
import re
import secrets
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
PKG_DIR = BACKEND_DIR / "tests" / "pg_concurrency"
GUARD_PATH = PKG_DIR / "guard.py"
RUNNER_PATH = PKG_DIR / "mutation_runner.py"

DEFAULT_IMAGE = os.environ.get("CARGOFLOW_PGTEST_IMAGE", "postgres:16")  # misma mayor que docker-compose.yml
LABEL = "cargoflow.pgtest"
UNUSED_DATABASE_URL = "postgresql+psycopg2://cf_unused:unused@127.0.0.1:1/cf_unused"
SCRUB_ENV = {"DATABASE_URL", "TEST_DATABASE_URL", "REDIS_URL", "N8N_WEBHOOK_URL", "N8N_WEBHOOK_SECRET", "JWT_SECRET"}

_TICK = threading.Event()


class LifecycleError(RuntimeError):
    pass


def _load_guard():
    spec = importlib.util.spec_from_file_location("cf_pg_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cf_pg_guard"] = module  # los dataclass con anotaciones diferidas lo necesitan
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


class Redactor:
    """Elimina de TODO lo que se imprime cualquier secreto generado por este proceso."""

    def __init__(self):
        self._secrets = set()

    def add(self, *values):
        self._secrets.update(v for v in values if v and len(v) >= 8)

    def __call__(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


REDACT = Redactor()


def log(message: str) -> None:
    print(f"[pg-test-db] {REDACT(message)}", flush=True)


# ---------------------------------------------------------------------------
# docker
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DockerTarget:
    """Contexto y endpoint de Docker registrados al CREAR el contenedor (ver capture_docker_target)."""

    context: str
    host: str


def docker(*args, input_text=None, extra_env=None, timeout=120, check=True, target=None):
    """Ejecuta `docker`. Con `target`, el comando se FIJA a ese contexto mediante `--context`: la
    bandera tiene prioridad sobre DOCKER_HOST/DOCKER_CONTEXT y sobre el contexto activo de
    ~/.docker, de modo que cambiarlos durante la ejecucion no redirige las operaciones."""
    env = dict(os.environ)
    env.update(extra_env or {})
    cmd = ["docker"]
    if target is not None:
        cmd += ["--context", target.context]
    cmd += list(args)
    try:
        proc = subprocess.run(
            cmd, input=input_text, capture_output=True, text=True, timeout=timeout, env=env
        )
    except FileNotFoundError:
        raise LifecycleError("docker no esta disponible en PATH") from None
    except subprocess.TimeoutExpired:
        raise LifecycleError(f"'docker {args[0]}' excedio {timeout}s") from None
    if check and proc.returncode != 0:
        raise LifecycleError(REDACT(f"'docker {args[0]}' fallo ({proc.returncode}): {proc.stderr.strip()[:400]}"))
    return proc


@dataclass
class Instance:
    run_id: str
    name: str
    token_dir: Path
    token_path: Path
    su_user: str
    database: str
    role: str
    su_password: str = field(repr=False, default="")
    role_password: str = field(repr=False, default="")
    container_id: str | None = None
    port: int | None = None
    run_attempted: bool = False  # True desde que se llama a `docker run`, aunque no devuelva id
    docker_target: DockerTarget | None = None  # contexto/endpoint registrado al crear el contenedor
    daemon_id: str | None = None  # ID del Docker Engine registrado al crear el contenedor

    @property
    def test_database_url(self) -> str:
        return f"postgresql+psycopg2://{self.role}:{self.role_password}@127.0.0.1:{self.port}/{self.database}"


_CONTEXT_FORMAT = "{{.Name}}|{{.Endpoints.docker.Host}}"
_CONTEXT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*")


def _parse_context(stdout: str) -> DockerTarget | None:
    name, sep, host = stdout.strip().partition("|")
    if not sep or _CONTEXT_NAME_RE.fullmatch(name) is None:
        return None
    if not host or "|" in host or any(ch.isspace() for ch in host):
        return None
    return DockerTarget(context=name, host=host)


def _resolve_addresses(hostname: str) -> list[str]:
    """Direcciones a las que resuelve `hostname` ([] si no se puede resolver). Aislada para poder simularla."""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return []
    return sorted({str(info[4][0]) for info in infos})


def _is_loopback_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def local_endpoint_problem(host: str) -> str | None:
    """None si el endpoint Docker `host` (normalizado) es LOCAL; si no, el motivo del rechazo.

    El laboratorio publica PostgreSQL en 127.0.0.1 y TEST_DATABASE_URL usa 127.0.0.1, asi que el
    puerto publicado solo es accesible desde pytest si el daemon esta en ESTE mismo entorno. Se
    admiten unicamente:
      * unix:///ruta/absoluta (socket Unix local);
      * tcp:// hacia una direccion de loopback VERIFICADA: IP literal de loopback (127.0.0.0/8, ::1)
        o `localhost` si resuelve exclusivamente a direcciones de loopback.
    Todo lo demas (ssh://, tcp:// remoto o con un nombre no verificable, npipe://, fd://, otros
    esquemas, credenciales en la URL) se rechaza: se falla cerrado.
    """
    scheme, sep, rest = host.partition("://")
    scheme = scheme.lower()
    if not sep:
        return "formato de endpoint no reconocido"
    if scheme == "unix":
        if rest.startswith("/") and "\x00" not in rest:
            return None
        return "el socket Unix debe indicarse con una ruta absoluta"
    if scheme == "ssh":
        return "contexto SSH remoto"
    if scheme != "tcp":
        return f"esquema {scheme}:// no admitido (solo unix:// local y tcp:// de loopback)"
    try:
        parts = urlsplit(host)
        hostname, port = parts.hostname, parts.port  # .port valida el numero
    except ValueError:
        return "endpoint TCP mal formado"
    if parts.username is not None or parts.password is not None:
        return "endpoint TCP con credenciales en la URL"
    if not hostname:
        return "endpoint TCP sin host"
    if port is not None and not 0 < port < 65536:
        return "puerto TCP fuera de rango"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        return None if address.is_loopback else f"TCP remoto: {hostname} no es una direccion de loopback"
    if hostname.lower() == "localhost":
        resolved = _resolve_addresses(hostname)
        if resolved and all(_is_loopback_address(item) for item in resolved):
            return None
        return "localhost no se resuelve exclusivamente a direcciones de loopback (o no se pudo resolver)"
    return f"TCP remoto: el nombre de host {hostname} no se puede verificar como loopback"


def _require_local_endpoint(target: DockerTarget) -> None:
    problem = local_endpoint_problem(target.host)
    if problem is None:
        return
    raise LifecycleError(
        f"el endpoint de Docker ({target.host}) no es local ({problem}): el laboratorio publica "
        "PostgreSQL en 127.0.0.1 y TEST_DATABASE_URL usa 127.0.0.1, de modo que el puerto publicado solo "
        "es accesible si el daemon esta en este mismo entorno. Solo se admiten el socket Unix local y "
        "TCP de loopback verificable (no se implementan tuneles); se aborta sin crear el contenedor"
    )


def _require_docker_host_identified(target: DockerTarget) -> None:
    """Con DOCKER_HOST definido, la CLI ignora el contexto activo y usa ese endpoint.

    `docker context inspect` solo identifica el destino pretendido si PUEDE DEMOSTRARSE que el
    contexto capturado ES el que DOCKER_HOST fija: el contexto 'default' y un endpoint IDENTICO,
    cadena a cadena, al valor de DOCKER_HOST. Cualquier otra cosa (valor vacio, contexto distinto,
    endpoint distinto o no normalizado, p. ej. `tcp://host` sin puerto) no se puede demostrar y se
    FALLA CERRADO: no se crea el contenedor ni se continua con el aprovisionamiento.
    """
    raw = os.environ.get("DOCKER_HOST")
    if raw is None:
        return
    if not raw.strip():
        problem = "esta definido pero vacio"
    elif target.context != "default":
        problem = f"esta definido, pero el contexto capturado es '{target.context}' y no 'default'"
    elif target.host != raw:
        problem = f"esta definido, pero no coincide exactamente con el endpoint del contexto capturado ({target.host})"
    else:
        return
    raise LifecycleError(
        f"DOCKER_HOST {problem}: no se puede demostrar que el contexto/endpoint capturado "
        f"({target.context}, {target.host}) sea el destino efectivo que se pretende usar; se aborta "
        "sin crear el contenedor. Defina DOCKER_HOST con el mismo formato normalizado que muestra "
        "`docker context inspect`, o elimine la variable y seleccione el destino con un contexto"
    )


def capture_docker_target() -> DockerTarget:
    """Contexto y endpoint EFECTIVOS ahora mismo (sin `--context`): los que usara `docker run`.

    Solo se acepta un endpoint LOCAL (socket Unix o TCP de loopback verificable): los contextos SSH
    y TCP remotos se rechazan (ver local_endpoint_problem). Con DOCKER_HOST definido ademas debe
    poder demostrarse que identifica el destino pretendido (ver _require_docker_host_identified).
    En ambos casos se falla cerrado: no se crea el contenedor.
    """
    proc = docker("context", "inspect", "--format", _CONTEXT_FORMAT, timeout=30)
    target = _parse_context(proc.stdout)
    if target is None:
        raise LifecycleError("no se pudo determinar el contexto/endpoint de Docker en uso")
    _require_local_endpoint(target)
    _require_docker_host_identified(target)
    return target


_DAEMON_ID_FORMAT = "{{.ID}}"
_DAEMON_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_.-]{7,127}")


def _query_daemon_id(target: DockerTarget) -> str | None:
    """ID del Docker Engine alcanzado con `target` (comando fijado a ese contexto), o None si no se
    pudo obtener un ID con formato valido (error, vacio, `<no value>`, texto inesperado)."""
    try:
        proc = docker("info", "--format", _DAEMON_ID_FORMAT, check=False, timeout=30, target=target)
    except LifecycleError:
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value if _DAEMON_ID_RE.fullmatch(value) else None


def capture_daemon_id(target: DockerTarget) -> str:
    """ID del Docker Engine AL CREAR. Sin un ID verificable no se puede identificar el daemon: falla cerrado."""
    daemon_id = _query_daemon_id(target)
    if daemon_id is None:
        raise LifecycleError(
            f"no se pudo obtener un ID valido del Docker Engine ({target.context}); sin el no se puede "
            "identificar el daemon que crea el contenedor: se aborta sin crearlo"
        )
    return daemon_id


def docker_target_verified(inst: Instance) -> bool:
    """True SOLO si el contexto registrado sigue existiendo, apunta al MISMO endpoint y ese endpoint
    sigue siendo el MISMO Docker Engine (mismo ID).

    Sin contexto o ID registrados, error al consultarlos, salida inesperada, renombrado, endpoint
    distinto o ID distinto => False: no se puede afirmar que Docker siga siendo el mismo daemon que
    creo el contenedor. Primero se consulta el almacen de contextos (sin tocar el daemon); solo si
    coincide se le pregunta el ID al daemon.
    """
    target = inst.docker_target
    if target is None or not inst.daemon_id:
        return False
    try:
        proc = docker("context", "inspect", target.context, "--format", _CONTEXT_FORMAT, check=False, timeout=30)
    except LifecycleError:
        return False
    if proc.returncode != 0 or _parse_context(proc.stdout) != target:
        return False
    return _query_daemon_id(target) == inst.daemon_id


def _write_private_file(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, (content + "\n").encode("ascii"))
    finally:
        os.close(fd)


def new_instance() -> tuple[Instance, str]:
    """Genera identificadores y credenciales aleatorios. Sin efectos en disco ni en Docker."""
    run_id = secrets.token_hex(8)
    token = secrets.token_hex(32)
    inst = Instance(
        run_id=run_id,
        name=f"cf-pgtest-{run_id}",
        token_dir=Path(),
        token_path=Path(),
        su_user=f"cf_su_{run_id}",
        database=f"cf_test_{run_id}",
        role=f"cf_test_user_{run_id}",
        su_password=secrets.token_hex(24),
        role_password=secrets.token_hex(24),
    )
    REDACT.add(token, inst.su_password, inst.role_password)
    return inst, token


def prepare_private_dir(inst: Instance, token: str) -> None:
    """Directorio privado (0700) FUERA del repo con el token en un archivo 0600."""
    token_dir = Path(
        tempfile.mkdtemp(prefix=f"cf-pgtest-{inst.run_id}-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    )
    inst.token_dir = token_dir  # registrado ya: el teardown lo limpia aunque falle lo siguiente
    inst.token_path = token_dir / "token"
    if token_dir.resolve().is_relative_to(REPO_ROOT.resolve()):
        raise LifecycleError("el directorio privado del token quedo dentro del repositorio")
    _write_private_file(inst.token_path, token)


def start_container(inst: Instance, image: str) -> None:
    # El contexto, el endpoint (local y verificado) y el ID del Docker Engine se registran AL CREAR y
    # se fijan/verifican en TODAS las operaciones posteriores. Si algo no se puede determinar, no se
    # crea nada (run_attempted sigue en False y la instancia no queda con valores parciales).
    target = capture_docker_target()
    daemon_id = capture_daemon_id(target)
    inst.docker_target = target
    inst.daemon_id = daemon_id
    log(f"contexto Docker fijado: {target.context} ({target.host}); ID del Docker Engine: {daemon_id}")
    inst.run_attempted = True  # si `docker run` expira o falla a medias, el contenedor puede existir
    proc = docker(
        "run", "-d", "--name", inst.name,
        "--label", f"{LABEL}=1",
        "--label", f"{LABEL}.run_id={inst.run_id}",
        "--label", f"{LABEL}.owner_pid={os.getpid()}",
        "-p", "127.0.0.1::5432",                     # SOLO loopback, puerto efimero
        "--tmpfs", "/var/lib/postgresql/data:rw,nosuid,size=512m",
        "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "1g",
        "-e", "POSTGRES_USER", "-e", "POSTGRES_PASSWORD",   # sin valor: se heredan del entorno, no de argv
        "-e", "POSTGRES_DB=postgres",
        "-e", "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
        image,
        "-c", "max_connections=60", "-c", "fsync=off", "-c", "synchronous_commit=off",
        "-c", "full_page_writes=off", "-c", "log_lock_waits=on", "-c", "deadlock_timeout=1s",
        extra_env={"POSTGRES_USER": inst.su_user, "POSTGRES_PASSWORD": inst.su_password},
        timeout=300,
        target=inst.docker_target,
    )
    container_id = proc.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", container_id):
        raise LifecycleError("docker run no devolvio un id de contenedor valido")
    inst.container_id = container_id  # registrado YA: el teardown puede destruirlo aunque falle lo siguiente
    log(f"contenedor {inst.name} creado (base {inst.database})")


def discover_port(inst: Instance) -> None:
    out = docker("port", inst.container_id, "5432/tcp", target=inst.docker_target).stdout.split()
    ports = []
    for item in out:
        match = re.fullmatch(r"127\.0\.0\.1:(\d+)", item)
        if match is None:
            raise LifecycleError(f"el puerto no esta publicado exclusivamente en 127.0.0.1: {item!r}")
        ports.append(int(match.group(1)))
    if len(ports) != 1:
        raise LifecycleError("se esperaba exactamente un puerto publicado")
    inst.port = ports[0]


def wait_ready(inst: Instance, deadline_s: int = 90) -> None:
    deadline = time.monotonic() + deadline_s
    ok = 0
    while time.monotonic() < deadline:
        state = docker("inspect", "-f", "{{.State.Running}}", inst.container_id, check=False,
                       target=inst.docker_target).stdout.strip()
        if state != "true":
            raise LifecycleError("el contenedor dejo de ejecutarse durante el arranque")
        probe = docker("exec", inst.container_id, "pg_isready", "-h", "127.0.0.1", "-p", "5432",
                       "-U", inst.su_user, check=False, timeout=15, target=inst.docker_target)
        ok = ok + 1 if probe.returncode == 0 else 0
        if ok >= 2:  # la imagen oficial arranca un servidor temporal de inicializacion antes del definitivo
            return
        _TICK.wait(1.0)
    raise LifecycleError(f"PostgreSQL no estuvo listo en {deadline_s}s")


def psql(inst: Instance, database: str, sql: str, *, tuples=False) -> str:
    args = ["exec", "-i", "-e", "PGPASSWORD", inst.container_id, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-U", inst.su_user, "-d", database]
    if tuples:
        args += ["-At"]
    # SQL por stdin y PGPASSWORD heredado del entorno: ni password ni token en argv.
    return docker(
        *args, input_text=sql, extra_env={"PGPASSWORD": inst.su_password}, target=inst.docker_target
    ).stdout


def provision(inst: Instance, token: str) -> None:
    for value, pattern in ((inst.role, r"cf_test_user_[0-9a-f]{16}"), (inst.database, r"cf_test_[0-9a-f]{16}")):
        if not re.fullmatch(pattern, value):
            raise LifecycleError("identificador generado con formato inesperado")  # defensa ante inyeccion
    token_hash = guard.token_sha256(token)
    sql = f"""
CREATE ROLE {inst.role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 20 PASSWORD '{inst.role_password}';
CREATE DATABASE {inst.database} OWNER {inst.role};
REVOKE ALL ON DATABASE {inst.database} FROM PUBLIC;
GRANT CONNECT ON DATABASE {inst.database} TO {inst.role};
\\connect {inst.database}
CREATE TABLE public.cf_test_sentinel (
  id integer PRIMARY KEY CHECK (id = 1),
  db_name text NOT NULL, run_id text NOT NULL, token_sha256 text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now());
INSERT INTO public.cf_test_sentinel (id, db_name, run_id, token_sha256)
  VALUES (1, '{inst.database}', '{inst.run_id}', '{token_hash}');
REVOKE ALL ON public.cf_test_sentinel FROM PUBLIC;
GRANT SELECT ON public.cf_test_sentinel TO {inst.role};
"""
    psql(inst, "postgres", sql)
    count = psql(inst, inst.database, "SELECT count(*) FROM public.cf_test_sentinel;", tuples=True).strip()
    if count != "1":
        raise LifecycleError("el sentinel no quedo creado")


# ---------------------------------------------------------------------------
# entorno del proceso hijo (pytest / runner)
# ---------------------------------------------------------------------------
def child_env(inst: Instance) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG") and k not in SCRUB_ENV}
    url = inst.test_database_url
    guard.validate_test_database_url(url)  # la misma guarda que aplican los tests
    env.update(
        TEST_DATABASE_URL=url,
        # Cualquier uso accidental del engine global de la app falla en lugar de tocar una base real.
        DATABASE_URL=UNUSED_DATABASE_URL,
        REDIS_URL="redis://127.0.0.1:1/0",
        PYTHONDONTWRITEBYTECODE="1",
        PGCONNECT_TIMEOUT="10",
    )
    return env


def unit_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG") and k not in SCRUB_ENV}
    env.update(DATABASE_URL=UNUSED_DATABASE_URL, REDIS_URL="redis://127.0.0.1:1/0", PYTHONDONTWRITEBYTECODE="1")
    return env


def run_unit_tests() -> int:
    log("tests unitarios de la guarda (sin Docker)")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/pg_concurrency", "-m", "pg_concurrency_unit",
         "-p", "no:cacheprovider", "-q"],
        cwd=BACKEND_DIR, env=unit_env(),
    ).returncode


# ---------------------------------------------------------------------------
# teardown seguro
# ---------------------------------------------------------------------------
def lookup_container(inst: Instance) -> tuple[str, str | None]:
    """Consulta a Docker por el NOMBRE del contenedor de esta ejecucion.

    Devuelve:
      ('absent',  None)  SOLO si Docker respondio con exito y confirma que no existe (o si nunca se
                          llego a invocar `docker run`);
      ('present', <id>)  si existe;
      ('unknown', None)  ante cualquier otra cosa: daemon caido, timeout, `docker` ausente, codigo de
                          salida distinto de 0 o salida inesperada. Un error al consultar NO es
                          "inexistente": el estado es incierto y no se destruye nada.
                          Tambien es 'unknown' si el contexto/endpoint/ID del Docker Engine registrados
                          al crear el contenedor no se pueden verificar o cambiaron: entonces no se
                          le consulta el contenedor al daemon (podria ser otro distinto del que lo creo).
    """
    if inst.container_id is None and not inst.run_attempted:
        return "absent", None
    if not docker_target_verified(inst):
        return "unknown", None
    try:
        proc = docker(
            "ps", "-a", "--no-trunc", "--filter", f"name=^/{inst.name}$", "--format", "{{.ID}}",
            check=False, timeout=30, target=inst.docker_target,
        )
    except LifecycleError:
        return "unknown", None
    if proc.returncode != 0:
        return "unknown", None
    ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not ids:
        return "absent", None
    if len(ids) == 1 and re.fullmatch(r"[0-9a-f]{64}", ids[0]):
        return "present", ids[0]
    return "unknown", None


def _is_running(inst: Instance, container_id: str) -> bool | None:
    """True/False si Docker lo confirma; None si no se pudo determinar."""
    try:
        proc = docker("inspect", "-f", "{{.State.Running}}", container_id, check=False, timeout=30,
                      target=inst.docker_target)
    except LifecycleError:
        return None
    out = proc.stdout.strip() if proc.returncode == 0 else ""
    return {"true": True, "false": False}.get(out)


def leak_reason(inst: Instance) -> str | None:
    """Motivo para CONSERVAR contenedor y credenciales, o None si es seguro destruir."""
    if inst.token_dir != Path():
        marker = inst.token_dir / guard.DIRTY_MARKER_NAME
        if marker.exists():
            return f"marcador de contaminacion: {marker.read_text(errors='replace').strip()[:300]}"
    state, found_id = lookup_container(inst)
    if state == "absent":
        return None
    if state == "unknown":
        verification = (
            "contexto/endpoint/ID del Docker Engine registrados"
            if inst.daemon_id
            else "contexto/endpoint registrados"
        )
        return (
            "estado incierto: no se pudo verificar si el contenedor existe (error al consultar Docker, "
            f"o los datos de {verification} no se pueden verificar o cambiaron)"
        )
    if inst.container_id and found_id != inst.container_id:
        return "estado incierto: el id del contenedor encontrado no coincide con el registrado"
    running = _is_running(inst, found_id)
    if running is None:
        return "estado incierto: no se pudo verificar si el contenedor esta en ejecucion"
    if not running or inst.port is None:
        return None
    try:
        out = psql(
            inst, inst.database,
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
            "AND pid <> pg_backend_pid() AND state <> 'idle';",
            tuples=True,
        ).strip()
    except LifecycleError as exc:
        return f"no se pudo comprobar sesiones activas ({exc})"
    return f"{out} sesion(es) activa(s) en la base de pruebas" if out != "0" else None


def _safe_rmtree(inst: Instance) -> None:
    """Elimina el directorio privado (token) SOLO si es el que creo este proceso.

      * Nunca se creo, o ya no existe        -> limpio: vuelve sin hacer nada.
      * Existe pero NO cumple las condiciones de seguridad (nombre de esta ejecucion, directorio
        real y no enlace simbolico, propiedad del usuario actual) -> LifecycleError: NO se borra
        nada y el teardown no puede declararse exitoso (conserva el directorio e informa el motivo).
      * Existe, es seguro y el borrado falla (rmtree sin ignore_errors), o tras borrar sigue
        existiendo, o su existencia no se puede comprobar -> LifecycleError. Solo "no existe"
        (FileNotFoundError) cuenta como limpio; un error de inspeccion NO prueba que desaparecio.
    Se inspecciona con lstat() (no sigue enlaces simbolicos): un enlace colgante tambien cuenta como
    "existe" y se rechaza.
    """
    path = inst.token_dir
    if path == Path():  # prepare_private_dir() nunca llego a crearlo
        return
    try:
        info = path.lstat()
    except FileNotFoundError:
        return  # ya no existe: limpio
    except OSError as exc:
        raise LifecycleError(
            f"no se pudo inspeccionar el directorio privado {path} ({exc.strerror or type(exc).__name__}); "
            "no se elimina"
        ) from None
    problems = []
    if not path.name.startswith(f"cf-pgtest-{inst.run_id}-"):
        problems.append("el nombre no corresponde a esta ejecucion")
    if stat.S_ISLNK(info.st_mode):
        problems.append("es un enlace simbolico")
    elif not stat.S_ISDIR(info.st_mode):
        problems.append("no es un directorio")
    if info.st_uid != os.getuid():
        problems.append("no pertenece al usuario actual")
    if problems:
        raise LifecycleError(
            f"el directorio privado {path} existe pero no cumple las condiciones de seguridad y NO se "
            f"elimina: {'; '.join(problems)}"
        )
    try:
        shutil.rmtree(path)  # SIN ignore_errors: un fallo de borrado no debe quedar oculto
    except FileNotFoundError:
        pass  # desaparecio entre la inspeccion y el borrado: se confirma justo debajo
    except OSError as exc:
        raise LifecycleError(
            f"no se pudo eliminar el directorio privado {path} ({exc.strerror or type(exc).__name__})"
        ) from None
    # Confirmacion: solo "no existe" (FileNotFoundError) prueba que desaparecio. Un error al
    # inspeccionar NO es evidencia de borrado (os.path.lexists() lo habria tomado por "no existe").
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise LifecycleError(
            f"no se pudo verificar que el directorio privado {path} fue eliminado "
            f"({exc.strerror or type(exc).__name__})"
        ) from None
    raise LifecycleError(f"no se pudo eliminar el directorio privado {path}")


def destroy(inst: Instance) -> None:
    """Destruye UNICAMENTE el contenedor creado por este proceso (id + etiquetas verificados).

    Las credenciales (directorio privado) solo se eliminan cuando el contenedor esta CONFIRMADO como
    inexistente o como eliminado. Con estado incierto lanza LifecycleError sin borrar nada.
    """
    state, found_id = lookup_container(inst)
    if state == "unknown":
        raise LifecycleError(
            "no se pudo verificar el estado del contenedor (consulta a Docker, o contexto/endpoint/ID "
            "del Docker Engine registrados); no se elimina nada"
        )
    if state == "present":
        if inst.container_id and found_id != inst.container_id:
            raise LifecycleError("el id del contenedor encontrado no coincide con el registrado: no se elimina")
        info = docker(
            "inspect", "-f",
            '{{.Id}}|{{index .Config.Labels "cargoflow.pgtest.run_id"}}|{{index .Config.Labels "cargoflow.pgtest.owner_pid"}}',
            found_id, check=False, timeout=30, target=inst.docker_target,
        )
        if info.returncode != 0:
            raise LifecycleError("no se pudieron verificar las etiquetas del contenedor: no se elimina")
        cid, run_id, owner = (info.stdout.strip().split("|") + ["", "", ""])[:3]
        if cid != found_id or run_id != inst.run_id or owner != str(os.getpid()):
            raise LifecycleError("el contenedor no coincide con el creado por este proceso: no se elimina")
        docker("rm", "-f", "-v", found_id, target=inst.docker_target)
        if lookup_container(inst)[0] != "absent":
            raise LifecycleError("no se pudo confirmar la eliminacion del contenedor; se conservan las credenciales")
        log(f"contenedor {inst.name} eliminado")
    _safe_rmtree(inst)  # solo se llega aqui con el contenedor confirmado como inexistente


def _docker_cmd(inst: Instance) -> str:
    """Prefijo `docker` para las instrucciones de recuperacion: con el MISMO contexto registrado."""
    if inst.docker_target is None:
        return "docker"
    return f"docker --context {shlex.quote(inst.docker_target.context)}"


def _report_retained(inst: Instance, reason: str) -> None:
    docker_cmd = _docker_cmd(inst)
    log(f"TEARDOWN NO COMPLETADO: {reason}")
    log(f"  contenedor: {inst.name} (id {inst.container_id or 'desconocido'}, puerto 127.0.0.1:{inst.port})")
    if inst.docker_target is not None:
        log(
            f"  contexto Docker registrado: {inst.docker_target.context} ({inst.docker_target.host}); "
            "use ese mismo contexto para recuperarlo"
        )
    else:
        log("  contexto Docker: no registrado (no se pudo determinar antes de crear el contenedor)")
    if inst.daemon_id:
        log(f"  ID del Docker Engine registrado: {inst.daemon_id}; compruebe con `{docker_cmd} info` que es el mismo")
    log(f"  directorio privado CONSERVADO (contiene el token): {inst.token_dir}")
    log(f"  verifique:  {docker_cmd} ps -a --filter 'name=^/{inst.name}$'")
    log(f"  y, cuando termine, elimine:  {docker_cmd} rm -f -v {inst.name}  &&  rm -rf {inst.token_dir}")


def teardown(inst: Instance) -> bool:
    """True SOLO si el contenedor quedo confirmado como eliminado/inexistente y el directorio privado
    se borro. False si se conservo algo: sesiones/hilos vivos, marcador de contaminacion o estado
    del contenedor incierto."""
    reason = leak_reason(inst)
    if reason:
        _report_retained(inst, reason)
        return False
    try:
        destroy(inst)
    except LifecycleError as exc:
        _report_retained(inst, f"teardown no confirmado: {exc}")
        return False
    return True


# ---------------------------------------------------------------------------
# comandos
# ---------------------------------------------------------------------------
def _with_instance(image: str, action) -> int:
    inst, token = new_instance()
    retained = False
    code = 2
    try:
        prepare_private_dir(inst, token)
        start_container(inst, image)
        discover_port(inst)
        wait_ready(inst)
        provision(inst, token)
        del token
        log(f"base {inst.database} lista en 127.0.0.1:{inst.port}")
        code = action(inst)
    except LifecycleError as exc:
        log(f"ERROR: {exc}")
        code = 2
    finally:
        try:
            retained = not teardown(inst)
        except LifecycleError as exc:
            _report_retained(inst, f"error inesperado en el teardown: {exc}")
            retained = True
    if retained and code == 0:
        code = 3
    return code


def _run_child(cmd, inst, timeout) -> int:
    try:
        return subprocess.run(cmd, cwd=BACKEND_DIR, env=child_env(inst), timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        log(f"timeout de {timeout}s: proceso terminado; se revisaran sesiones vivas antes del teardown")
        return 124


def cmd_check(_args) -> int:
    ok = True
    try:
        version = docker("version", "--format", "{{.Server.Version}}", timeout=30).stdout.strip()
        log(f"docker OK (servidor {version})")
    except LifecycleError as exc:
        log(f"docker NO disponible: {exc}")
        ok = False
    for module in ("psycopg2", "sqlalchemy", "fastapi", "pytest"):
        if importlib.util.find_spec(module) is None:
            log(f"falta el paquete de Python: {module}")
            ok = False
        else:
            log(f"paquete {module} importable")
    return 0 if ok else 2


def cmd_suite(args) -> int:
    rc = run_unit_tests()
    if rc != 0:
        return rc

    def action(inst):
        cmd = [sys.executable, "-m", "pytest", "tests/pg_concurrency", "-m", "pg_concurrency",
               "-p", "no:cacheprovider", f"--pg-token-file={inst.token_path}", *args.pytest_args]
        return _run_child(cmd, inst, args.timeout)

    return _with_instance(args.image, action)


def cmd_mutations(args) -> int:
    rc = run_unit_tests()
    if rc != 0:
        return rc

    def action(inst):
        cmd = [sys.executable, str(RUNNER_PATH), "--backend-dir", str(BACKEND_DIR),
               "--repo-root", str(REPO_ROOT),
               "--token-file", str(inst.token_path), "--timeout", str(args.timeout)]
        if args.only:
            cmd += ["--only", *args.only]
        return _run_child(cmd, inst, args.timeout * (2 + len(args.only or range(4))))

    return _with_instance(args.image, action)


def cmd_list(_args) -> int:
    out = docker(
        "ps", "-a", "--filter", f"label={LABEL}=1", "--format",
        '{{.Names}}\t{{.Status}}\t{{.Label "cargoflow.pgtest.owner_pid"}}',
    ).stdout.strip()
    print(out or "(sin contenedores de pruebas)")
    return 0


def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # el finally ejecuta el teardown seguro
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("list").set_defaults(func=cmd_list)

    p_suite = sub.add_parser("suite")
    p_suite.add_argument("--image", default=DEFAULT_IMAGE)
    p_suite.add_argument("--timeout", type=int, default=900)
    p_suite.add_argument("pytest_args", nargs="*", help="argumentos extra de pytest (tras --)")
    p_suite.set_defaults(func=cmd_suite)

    p_mut = sub.add_parser("mutations")
    p_mut.add_argument("--image", default=DEFAULT_IMAGE)
    p_mut.add_argument("--timeout", type=int, default=900)
    p_mut.add_argument("--only", nargs="*", default=[], help="M1-V M1-D M2 M3")
    p_mut.set_defaults(func=cmd_mutations)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
