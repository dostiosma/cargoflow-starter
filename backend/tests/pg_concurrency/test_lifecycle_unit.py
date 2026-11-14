"""Pruebas unitarias del teardown de infrastructure/test-db/pg_test_db.py (sin Docker).

Se sustituye `pg_test_db.docker` por un DOBLE (`FakeDocker`) que responde como lo haria el
comando real, incluidos sus fallos; ningun proceso se lanza y no se toca ningun contenedor.
Cubren `lookup_container`, `destroy` y `teardown` en estos escenarios:

  * contenedor ausente (Docker lo confirma);
  * contenedor presente;
  * Docker inaccesible (binario ausente/timeout, daemon caido, salida inesperada);
  * `docker rm` fallido;
  * contenedor todavia presente tras `docker rm`;
  * fallo al eliminar el directorio privado;
  * contexto/endpoint de Docker: se registra al crear el contenedor, se FIJA (`--context`) en
    todas las operaciones y, si no se puede verificar o cambia (renombrado, endpoint distinto,
    borrado, sin registrar), el estado es desconocido y se conserva todo;
  * endpoint Docker LOCAL: solo el socket Unix y TCP de loopback verificable; SSH y TCP remotos
    se rechazan antes de crear nada;
  * ID del Docker Engine: se registra al crear y se verifica antes de cada consulta (otro ID o ID
    no verificable => estado desconocido);
  * directorio privado: si existe pero no es seguro (nombre, tipo, enlace simbolico, propietario)
    se lanza LifecycleError y el teardown no es exitoso; si ya no existe, es limpio.

Propiedad central: ante CUALQUIER estado incierto o fallo, no se borran las credenciales
(directorio privado con el token), el teardown no se declara exitoso y se informa como
recuperar el contenedor.

Marcador `pg_concurrency_unit`: opt-in, como el resto del paquete (pg_test_db.py los ejecuta
antes de crear ningun contenedor).
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [
    pytest.mark.pg_concurrency_unit,
    pytest.mark.skipif(not hasattr(os, "getuid"), reason="el ciclo de vida usa os.getuid (POSIX)"),
]

LIFECYCLE_PATH = Path(__file__).resolve().parents[3] / "infrastructure" / "test-db" / "pg_test_db.py"

CID = "ab" * 32        # id completo (64 hex) del contenedor "propio"
OTHER_CID = "cd" * 32  # id de un contenedor distinto
RUN_ID = "0123456789abcdef"
TOKEN = "ef" * 32

UNKNOWN_PS_MODES = ["unreachable", "daemon_error", "garbage", "two_ids"]
DEFAULT_TARGET = ("default", "unix:///var/run/docker.sock")  # (contexto, endpoint) registrados
CONTEXT_PROBLEMS = ["error", "unreachable", "garbage", "renamed", "endpoint_changed"]
DAEMON_ID = "7TRN:IPZB:QYBB:VPBQ:UWZP:CKPB:ZXB7:EGM2"        # ID del Docker Engine registrado
OTHER_DAEMON_ID = "OTHR:IPZB:QYBB:VPBQ:UWZP:CKPB:ZXB7:EGM2"  # ID de OTRO Docker Engine
# `docker info` no devuelve un ID verificable / devuelve el de otro daemon:
DAEMON_PROBLEMS = ["other", "empty", "garbage", "error", "unreachable"]


@pytest.fixture(scope="module")
def lifecycle():
    """Carga pg_test_db.py por ruta (no es un paquete). Solo ejecuta definiciones: no lanza nada."""
    if not LIFECYCLE_PATH.is_file():
        pytest.fail(f"no se encuentra {LIFECYCLE_PATH}", pytrace=False)
    name = "cf_pg_test_db_under_test"
    keys = (name, "cf_pg_guard")
    previous = {key: sys.modules.get(key) for key in keys}
    spec = importlib.util.spec_from_file_location(name, LIFECYCLE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # los dataclass con anotaciones diferidas lo necesitan
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


class FakeDocker:
    """Doble de `pg_test_db.docker`. Registra cada llamada y nunca ejecuta procesos.

    ps_plan: modo de respuesta de cada `docker ps` sucesivo (se repite el ultimo):
      state        -> refleja el estado simulado (presente/ausente)
      unreachable  -> LifecycleError, como cuando falta el binario o expira el timeout
      daemon_error -> codigo de salida 1 ("Cannot connect to the Docker daemon")
      garbage      -> salida que no es un id
      two_ids      -> mas de un id
      other_id     -> un id distinto del registrado
    rm: ok | fail (LifecycleError, como `docker()` con check=True) | noop (exito aparente, sigue presente)
    labels: ok | foreign (otro owner_pid) | error (inspect devuelve codigo != 0)
    running_inspect: ok | error
    context_plan: modo de cada `docker context inspect` sucesivo (se repite el ultimo):
      ok               -> el contexto registrado sigue igual (mismo nombre y endpoint)
      error            -> codigo de salida 1 (contexto inexistente / no verificable)
      unreachable      -> LifecycleError (binario ausente o timeout)
      garbage          -> salida con formato inesperado
      renamed          -> otro nombre de contexto
      endpoint_changed -> mismo nombre, endpoint distinto
    daemon_plan: modo de cada `docker info --format {{.ID}}` sucesivo (se repite el ultimo):
      ok          -> el ID del Docker Engine registrado (DAEMON_ID)
      other       -> el ID de OTRO daemon
      empty       -> salida vacia
      garbage     -> salida sin formato de ID (`<no value>`)
      error       -> codigo de salida 1
      unreachable -> LifecycleError (binario ausente o timeout)
    """

    def __init__(self, lifecycle, inst, *, exists=True, running=False, ps_plan=("state",), rm="ok",
                 labels="ok", running_inspect="ok", sessions="0\n", context_plan=("ok",),
                 daemon_plan=("ok",)):
        self.lc = lifecycle
        self.inst = inst
        self.exists = exists
        self.running = running
        self.ps_plan = list(ps_plan)
        self.rm_mode = rm
        self.labels_mode = labels
        self.running_inspect = running_inspect
        self.sessions = sessions
        self.context_plan = list(context_plan)
        self.daemon_plan = list(daemon_plan)
        # Contexto "real" del doble: el que devuelve `docker context inspect` cuando todo va bien.
        self.context_name = DEFAULT_TARGET[0]
        self.context_host = DEFAULT_TARGET[1]
        self.daemon_id = DAEMON_ID
        self.calls = []            # TODAS las llamadas, incluidas las de `docker context`
        self.targets = []          # (verbo, target) de las llamadas que hablan con el DAEMON
        self.context_targets = []  # target con el que se invoco cada `docker context ...`
        self._ps_calls = 0
        self._context_calls = 0
        self._info_calls = 0

    @property
    def verbs(self):
        """Operaciones sobre el contenedor (excluye las de VERIFICACION: `docker context` e `info`)."""
        return [call[0] for call in self.calls if call[0] not in ("context", "info")]

    @property
    def context_checks(self):
        return len(self.context_targets)

    @property
    def info_calls(self):
        """Cuantas veces se le pregunto el ID al daemon (`docker info`)."""
        return sum(1 for call in self.calls if call[0] == "info")

    def _done(self, args, rc=0, out="", err="", check=True):
        if check and rc != 0:
            raise self.lc.LifecycleError(f"'docker {args[0]}' fallo ({rc}): {err}")
        return subprocess.CompletedProcess(["docker", *args], rc, out, err)

    def __call__(self, *args, input_text=None, extra_env=None, timeout=120, check=True, target=None):
        self.calls.append(args)
        if args[0] == "context":
            self.context_targets.append(target)
        else:
            self.targets.append((args[0], target))
        handler = getattr(self, f"_{args[0]}", None)
        if handler is None:
            raise AssertionError(f"comando docker no previsto por el doble: {args!r}")
        return handler(args, check)

    def _context(self, args, check):
        # Verificacion: ("context", "inspect", <nombre>, "--format", FMT)
        # Captura:      ("context", "inspect", "--format", FMT)   (contexto efectivo, sin nombre)
        assert args[:2] == ("context", "inspect") and args[-2] == "--format", args
        mode = self.context_plan[min(self._context_calls, len(self.context_plan) - 1)]
        self._context_calls += 1
        if mode == "ok":
            return self._done(args, out=f"{self.context_name}|{self.context_host}\n", check=check)
        if mode == "error":
            return self._done(args, rc=1, err="context not found", check=check)
        if mode == "unreachable":
            raise self.lc.LifecycleError("docker no esta disponible en PATH")
        if mode == "garbage":
            return self._done(args, out="no-es-un-contexto\n", check=check)
        if mode == "renamed":
            return self._done(args, out=f"otro-contexto|{self.context_host}\n", check=check)
        if mode == "endpoint_changed":
            return self._done(args, out=f"{self.context_name}|tcp://10.0.0.9:2376\n", check=check)
        raise AssertionError(f"modo de context desconocido: {mode}")

    def _info(self, args, check):
        assert args == ("info", "--format", "{{.ID}}"), args
        mode = self.daemon_plan[min(self._info_calls, len(self.daemon_plan) - 1)]
        self._info_calls += 1
        if mode == "ok":
            return self._done(args, out=f"{self.daemon_id}\n", check=check)
        if mode == "other":
            return self._done(args, out=f"{OTHER_DAEMON_ID}\n", check=check)
        if mode == "empty":
            return self._done(args, out="\n", check=check)
        if mode == "garbage":
            return self._done(args, out="<no value>\n", check=check)
        if mode == "error":
            return self._done(args, rc=1, err="Cannot connect to the Docker daemon", check=check)
        if mode == "unreachable":
            raise self.lc.LifecycleError("docker no esta disponible en PATH")
        raise AssertionError(f"modo de info desconocido: {mode}")

    def _run(self, args, check):
        assert "--name" in args and self.inst.name in args, args
        return self._done(args, out=CID + "\n", check=check)

    def _ps(self, args, check):
        # La consulta debe ser por el NOMBRE exacto de este contenedor e incluir los detenidos.
        assert "-a" in args and f"name=^/{self.inst.name}$" in args, args
        mode = self.ps_plan[min(self._ps_calls, len(self.ps_plan) - 1)]
        self._ps_calls += 1
        if mode == "state":
            return self._done(args, out=(CID + "\n") if self.exists else "", check=check)
        if mode == "unreachable":
            raise self.lc.LifecycleError("docker no esta disponible en PATH")
        if mode == "daemon_error":
            return self._done(args, rc=1, err="Cannot connect to the Docker daemon", check=check)
        if mode == "garbage":
            return self._done(args, out="no-es-un-id\n", check=check)
        if mode == "two_ids":
            return self._done(args, out=f"{CID}\n{OTHER_CID}\n", check=check)
        if mode == "other_id":
            return self._done(args, out=OTHER_CID + "\n", check=check)
        raise AssertionError(f"modo de ps desconocido: {mode}")

    def _inspect(self, args, check):
        fmt = args[2]
        if "State.Running" in fmt:
            if self.running_inspect == "error":
                return self._done(args, rc=1, err="inspect failed", check=check)
            return self._done(args, out="true\n" if self.running else "false\n", check=check)
        if self.labels_mode == "error":
            return self._done(args, rc=1, err="inspect failed", check=check)
        owner = str(os.getpid()) if self.labels_mode == "ok" else "0"  # "0": ningun proceso real
        return self._done(args, out=f"{CID}|{RUN_ID}|{owner}\n", check=check)

    def _rm(self, args, check):
        assert args == ("rm", "-f", "-v", CID), args
        if self.rm_mode == "fail":
            return self._done(args, rc=1, err="permission denied", check=check)
        if self.rm_mode == "ok":
            self.exists = False
        return self._done(args, check=check)  # "noop": exito aparente y el contenedor sigue ahi

    def _exec(self, args, check):
        assert "psql" in args, args
        return self._done(args, out=self.sessions, check=check)


@pytest.fixture()
def env(lifecycle, tmp_path, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)  # cada prueba decide si DOCKER_HOST esta definido
    token_dir = tmp_path / f"cf-pgtest-{RUN_ID}-unit"
    token_dir.mkdir(mode=0o700)
    token_path = token_dir / "token"
    token_path.write_text(TOKEN + "\n")
    os.chmod(token_path, 0o600)
    inst = lifecycle.Instance(
        run_id=RUN_ID,
        name=f"cf-pgtest-{RUN_ID}",
        token_dir=token_dir,
        token_path=token_path,
        su_user=f"cf_su_{RUN_ID}",
        database=f"cf_test_{RUN_ID}",
        role=f"cf_test_user_{RUN_ID}",
        container_id=CID,
        port=54321,
        run_attempted=True,
        docker_target=lifecycle.DockerTarget(*DEFAULT_TARGET),
        daemon_id=DAEMON_ID,
    )

    def build(**kwargs):
        fake = FakeDocker(lifecycle, inst, **kwargs)
        monkeypatch.setattr(lifecycle, "docker", fake)
        return fake

    return SimpleNamespace(inst=inst, build=build, token_dir=token_dir, token_path=token_path)


def assert_credentials_intact(env):
    assert env.token_dir.is_dir(), "el directorio privado se borro"
    assert env.token_path.read_text().strip() == TOKEN, "el token se altero o se borro"


def assert_recovery_info(env, output, docker_cmd="docker --context default", daemon_id=DAEMON_ID):
    """El informe indica el motivo, que se conserva el directorio privado y COMO recuperar el
    contenedor: con el MISMO contexto Docker (y el ID del Docker Engine) registrados al crearlo."""
    expected = [
        "TEARDOWN NO COMPLETADO",
        "CONSERVADO",
        f"{docker_cmd} ps -a --filter 'name=^/{env.inst.name}$'",
        f"{docker_cmd} rm -f -v {env.inst.name}",
        f"rm -rf {env.inst.token_dir}",
    ]
    if daemon_id:
        expected.append(f"ID del Docker Engine registrado: {daemon_id}")
    for fragment in expected:
        assert fragment in output, f"falta en el informe de recuperacion: {fragment!r}\n{output}"


def assert_all_pinned(fake, inst):
    """Todo comando que habla con el daemon se fijo al contexto registrado; las consultas de
    `docker context` se hacen sin fijar (inspeccionan el almacen de contextos, no el daemon)."""
    assert fake.targets, "el doble no recibio ninguna operacion contra el daemon"
    assert all(target == inst.docker_target for _verb, target in fake.targets), fake.targets
    assert all(target is None for target in fake.context_targets), fake.context_targets


# ---------------------------------------------------------------------------
# lookup_container
# ---------------------------------------------------------------------------
def test_lookup_absent_when_docker_confirms_it(lifecycle, env):
    fake = env.build(exists=False)
    assert lifecycle.lookup_container(env.inst) == ("absent", None)
    assert fake.verbs == ["ps"]


def test_lookup_absent_without_asking_docker_if_run_was_never_attempted(lifecycle, env):
    env.inst.container_id = None
    env.inst.run_attempted = False
    fake = env.build()
    assert lifecycle.lookup_container(env.inst) == ("absent", None)
    assert fake.calls == []


def test_lookup_after_a_run_attempt_needs_docker_to_confirm_absence(lifecycle, env):
    env.inst.container_id = None  # `docker run` expiro: pudo crear el contenedor
    env.build(exists=False)
    assert lifecycle.lookup_container(env.inst) == ("absent", None)
    env.build(ps_plan=["unreachable"])
    assert lifecycle.lookup_container(env.inst) == ("unknown", None)


def test_lookup_present(lifecycle, env):
    fake = env.build(exists=True)
    assert lifecycle.lookup_container(env.inst) == ("present", CID)
    assert fake.verbs == ["ps"]


@pytest.mark.parametrize("mode", UNKNOWN_PS_MODES)
def test_lookup_is_unknown_on_docker_errors_or_unexpected_output(lifecycle, env, mode):
    env.build(ps_plan=[mode])
    assert lifecycle.lookup_container(env.inst) == ("unknown", None)


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------
def test_destroy_absent_container_removes_credentials_without_docker_rm(lifecycle, env):
    fake = env.build(exists=False)
    lifecycle.destroy(env.inst)
    assert fake.verbs == ["ps"]
    assert not env.token_dir.exists()


def test_destroy_present_container_verifies_removes_confirms_then_removes_credentials(lifecycle, env):
    fake = env.build(exists=True)
    lifecycle.destroy(env.inst)
    assert fake.verbs == ["ps", "inspect", "rm", "ps"]  # busca, verifica etiquetas, borra, confirma
    assert fake.context_checks == 2  # el contexto se verifica antes de cada busqueda (inicial y de confirmacion)
    assert fake.info_calls == 2      # y tambien el ID del Docker Engine
    assert_all_pinned(fake, env.inst)
    assert not env.token_dir.exists()


@pytest.mark.parametrize("mode", UNKNOWN_PS_MODES)
def test_destroy_with_unknown_state_touches_nothing(lifecycle, env, mode):
    fake = env.build(ps_plan=[mode])
    with pytest.raises(lifecycle.LifecycleError, match="no se pudo verificar el estado del contenedor"):
        lifecycle.destroy(env.inst)
    assert fake.verbs == ["ps"]
    assert_credentials_intact(env)


def test_destroy_refuses_a_container_with_a_different_id(lifecycle, env):
    fake = env.build(ps_plan=["other_id"])
    with pytest.raises(lifecycle.LifecycleError, match="no coincide con el registrado"):
        lifecycle.destroy(env.inst)
    assert "rm" not in fake.verbs
    assert_credentials_intact(env)


def test_destroy_refuses_a_container_not_created_by_this_process(lifecycle, env):
    fake = env.build(labels="foreign")
    with pytest.raises(lifecycle.LifecycleError, match="no coincide con el creado por este proceso"):
        lifecycle.destroy(env.inst)
    assert "rm" not in fake.verbs
    assert_credentials_intact(env)


def test_destroy_keeps_everything_if_labels_cannot_be_verified(lifecycle, env):
    fake = env.build(labels="error")
    with pytest.raises(lifecycle.LifecycleError, match="no se pudieron verificar las etiquetas"):
        lifecycle.destroy(env.inst)
    assert "rm" not in fake.verbs
    assert_credentials_intact(env)


def test_destroy_docker_rm_failure_keeps_credentials(lifecycle, env):
    fake = env.build(rm="fail")
    with pytest.raises(lifecycle.LifecycleError, match="docker rm"):
        lifecycle.destroy(env.inst)
    assert fake.verbs == ["ps", "inspect", "rm"]
    assert_credentials_intact(env)


def test_destroy_container_still_present_after_rm_keeps_credentials(lifecycle, env):
    fake = env.build(rm="noop")
    with pytest.raises(lifecycle.LifecycleError, match="no se pudo confirmar la eliminacion"):
        lifecycle.destroy(env.inst)
    assert fake.verbs == ["ps", "inspect", "rm", "ps"]
    assert_credentials_intact(env)


def test_destroy_unverifiable_state_after_rm_keeps_credentials(lifecycle, env):
    fake = env.build(ps_plan=["state", "unreachable"])  # el `ps` que confirma el borrado falla
    with pytest.raises(lifecycle.LifecycleError, match="no se pudo confirmar la eliminacion"):
        lifecycle.destroy(env.inst)
    assert fake.verbs == ["ps", "inspect", "rm", "ps"]
    assert_credentials_intact(env)


@pytest.mark.parametrize("exists", [False, True], ids=["container-absent", "container-removed"])
def test_destroy_reports_failure_to_remove_the_private_dir(lifecycle, env, monkeypatch, exists):
    env.build(exists=exists)
    with monkeypatch.context() as patch:
        # Un rmtree que "no falla" pero no borra (no-op): el directorio sigue ahi y la comprobacion
        # posterior con lstat debe detectarlo y no darlo por borrado.
        patch.setattr(lifecycle.shutil, "rmtree", lambda *args, **kwargs: None)
        with pytest.raises(lifecycle.LifecycleError, match="no se pudo eliminar el directorio privado"):
            lifecycle.destroy(env.inst)
    assert_credentials_intact(env)


# ---------------------------------------------------------------------------
# contexto/endpoint de Docker
# ---------------------------------------------------------------------------
def test_docker_wrapper_pins_the_recorded_context_with_the_context_flag(lifecycle, monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.subprocess, "run", fake_run)
        lifecycle.docker("ps")
        lifecycle.docker("ps", target=lifecycle.DockerTarget("remoto", "ssh://usuario@host"))
    assert seen == [["docker", "ps"], ["docker", "--context", "remoto", "ps"]]


def test_capture_docker_target_reads_the_effective_context(lifecycle, env):
    fake = env.build()
    assert lifecycle.capture_docker_target() == lifecycle.DockerTarget(*DEFAULT_TARGET)
    assert fake.calls == [("context", "inspect", "--format", lifecycle._CONTEXT_FORMAT)]
    assert fake.context_targets == [None]  # contexto EFECTIVO: no se fija a ninguno


@pytest.mark.parametrize("problem", ["error", "unreachable", "garbage"])
def test_capture_docker_target_fails_if_the_context_cannot_be_determined(lifecycle, env, problem):
    env.build(context_plan=[problem])
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.capture_docker_target()


def test_start_container_records_the_context_and_pins_docker_run(lifecycle, env):
    env.inst.docker_target = None
    env.inst.container_id = None
    env.inst.run_attempted = False
    fake = env.build()
    lifecycle.start_container(env.inst, "postgres:16")
    assert env.inst.docker_target == lifecycle.DockerTarget(*DEFAULT_TARGET)
    assert env.inst.run_attempted is True and env.inst.container_id == CID
    assert env.inst.daemon_id == DAEMON_ID  # el ID del Docker Engine se registra antes de crear
    # `docker info` (ID) y `docker run` van fijados al contexto registrado
    assert fake.targets == [("info", env.inst.docker_target), ("run", env.inst.docker_target)]
    assert fake.context_targets == [None]


def test_start_container_creates_nothing_if_the_context_cannot_be_determined(lifecycle, env):
    env.inst.docker_target = None
    env.inst.container_id = None
    env.inst.run_attempted = False
    fake = env.build(context_plan=["error"])
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.start_container(env.inst, "postgres:16")
    assert "run" not in fake.verbs
    assert env.inst.run_attempted is False and env.inst.docker_target is None


DOCKER_HOST_VALUE = "tcp://127.0.0.1:2375"  # loopback: la regla de endpoint local lo admite

# (id, valor de DOCKER_HOST, atributos del doble). En todos, el destino pretendido NO puede demostrarse.
DOCKER_HOST_UNPROVABLE = [
    ("endpoint-differs", DOCKER_HOST_VALUE, dict(context_host="unix:///var/run/docker.sock")),
    ("not-normalized-no-port", "tcp://127.0.0.1", dict(context_host=DOCKER_HOST_VALUE)),
    ("trailing-slash", "unix:///var/run/docker.sock/", dict(context_host="unix:///var/run/docker.sock")),
    ("leading-whitespace", " " + DOCKER_HOST_VALUE, dict(context_host=DOCKER_HOST_VALUE)),
    ("context-is-not-default", DOCKER_HOST_VALUE, dict(context_name="remoto", context_host=DOCKER_HOST_VALUE)),
    ("defined-but-empty", "", dict()),
    ("defined-but-blank", "   ", dict()),
]


def build_with_docker_host(env, monkeypatch, value, **attributes):
    monkeypatch.setenv("DOCKER_HOST", value)
    fake = env.build()
    for name, attribute in attributes.items():
        setattr(fake, name, attribute)
    return fake


def test_capture_accepts_docker_host_only_when_it_is_proven_to_be_the_context_endpoint(
    lifecycle, env, monkeypatch
):
    build_with_docker_host(env, monkeypatch, DOCKER_HOST_VALUE, context_host=DOCKER_HOST_VALUE)
    assert lifecycle.capture_docker_target() == lifecycle.DockerTarget("default", DOCKER_HOST_VALUE)


@pytest.mark.parametrize(
    "value,attributes", [case[1:] for case in DOCKER_HOST_UNPROVABLE], ids=[case[0] for case in DOCKER_HOST_UNPROVABLE]
)
def test_capture_fails_closed_if_docker_host_cannot_be_proven_to_be_the_effective_target(
    lifecycle, env, monkeypatch, value, attributes
):
    build_with_docker_host(env, monkeypatch, value, **attributes)
    with pytest.raises(lifecycle.LifecycleError, match="DOCKER_HOST"):
        lifecycle.capture_docker_target()


@pytest.mark.parametrize(
    "value,attributes", [case[1:] for case in DOCKER_HOST_UNPROVABLE], ids=[case[0] for case in DOCKER_HOST_UNPROVABLE]
)
def test_start_container_creates_nothing_if_docker_host_cannot_be_proven(
    lifecycle, env, monkeypatch, value, attributes
):
    env.inst.docker_target = None
    env.inst.container_id = None
    env.inst.run_attempted = False
    fake = build_with_docker_host(env, monkeypatch, value, **attributes)
    with pytest.raises(lifecycle.LifecycleError, match="DOCKER_HOST"):
        lifecycle.start_container(env.inst, "postgres:16")
    assert fake.verbs == []  # ni `docker run` ni ninguna otra operacion contra el daemon
    assert env.inst.run_attempted is False and env.inst.docker_target is None and env.inst.container_id is None


def test_start_container_proceeds_with_docker_host_when_it_is_proven(lifecycle, env, monkeypatch):
    env.inst.docker_target = None
    env.inst.container_id = None
    env.inst.run_attempted = False
    fake = build_with_docker_host(env, monkeypatch, DOCKER_HOST_VALUE, context_host=DOCKER_HOST_VALUE)
    lifecycle.start_container(env.inst, "postgres:16")
    assert env.inst.docker_target == lifecycle.DockerTarget("default", DOCKER_HOST_VALUE)
    # el ID del daemon y `docker run` se piden al destino demostrado (contexto fijado)
    assert fake.targets == [("info", env.inst.docker_target), ("run", env.inst.docker_target)]


def test_with_instance_stops_before_provisioning_and_cleans_up_if_docker_host_cannot_be_proven(
    lifecycle, env, monkeypatch, tmp_path, capsys
):
    runtime_dir = tmp_path / "xdg"
    runtime_dir.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))  # alli crea prepare_private_dir su directorio
    fake = build_with_docker_host(env, monkeypatch, DOCKER_HOST_VALUE)  # el contexto efectivo es el socket local
    actions = []
    code = lifecycle._with_instance("postgres:16", lambda inst: actions.append(inst) or 0)
    assert code == 2
    assert actions == [], "no debe ejecutarse ninguna accion tras un fallo cerrado"
    assert fake.verbs == [], "no se crea el contenedor ni se aprovisiona (sin run/port/exec/psql)"
    assert list(runtime_dir.iterdir()) == [], "el directorio privado del token debe limpiarse"
    assert "DOCKER_HOST" in capsys.readouterr().out


def test_lookup_verifies_the_recorded_context_and_pins_the_query(lifecycle, env):
    fake = env.build(exists=True)
    assert lifecycle.lookup_container(env.inst) == ("present", CID)
    assert fake.context_checks == 1
    assert fake.info_calls == 1  # el ID del Docker Engine se verifica tras el contexto
    assert_all_pinned(fake, env.inst)


@pytest.mark.parametrize("problem", CONTEXT_PROBLEMS)
def test_lookup_is_unknown_and_asks_the_daemon_nothing_if_the_context_cannot_be_verified(
    lifecycle, env, problem
):
    fake = env.build(context_plan=[problem])
    assert lifecycle.lookup_container(env.inst) == ("unknown", None)
    assert fake.verbs == []  # ni `ps`: el daemon podria no ser el que creo el contenedor
    assert fake.info_calls == 0  # ni siquiera su ID: primero debe verificarse el contexto


def test_lookup_is_unknown_without_a_recorded_context(lifecycle, env):
    env.inst.docker_target = None  # se intento crear, pero no hay contexto registrado
    fake = env.build()
    assert lifecycle.lookup_container(env.inst) == ("unknown", None)
    assert fake.calls == []


@pytest.mark.parametrize("problem", CONTEXT_PROBLEMS)
def test_destroy_with_an_unverifiable_or_changed_context_touches_nothing(lifecycle, env, problem):
    fake = env.build(context_plan=[problem])
    with pytest.raises(lifecycle.LifecycleError, match="no se pudo verificar el estado del contenedor"):
        lifecycle.destroy(env.inst)
    assert fake.verbs == []
    assert_credentials_intact(env)


def test_destroy_context_changing_before_the_removal_is_confirmed_keeps_credentials(lifecycle, env):
    fake = env.build(context_plan=["ok", "endpoint_changed"])  # la busqueda de confirmacion ya no verifica
    with pytest.raises(lifecycle.LifecycleError, match="no se pudo confirmar la eliminacion"):
        lifecycle.destroy(env.inst)
    assert fake.verbs == ["ps", "inspect", "rm"]
    assert_credentials_intact(env)


# ---------------------------------------------------------------------------
# _safe_rmtree: el directorio privado
# ---------------------------------------------------------------------------
def make_unsafe(kind, tmp_path, env):
    """Crea una ruta de directorio privado NO segura; devuelve (ruta, fragmento del motivo esperado)."""
    prefix = f"cf-pgtest-{RUN_ID}-"
    if kind == "wrong-name":
        path = tmp_path / "otro-directorio"
        path.mkdir(mode=0o700)
        (path / "token").write_text(TOKEN)
        return path, "el nombre no corresponde a esta ejecucion"
    if kind == "symlink-to-dir":
        path = tmp_path / (prefix + "enlace")
        path.symlink_to(env.token_dir, target_is_directory=True)
        return path, "es un enlace simbolico"
    if kind == "dangling-symlink":
        path = tmp_path / (prefix + "colgante")
        path.symlink_to(tmp_path / "no-existe")
        return path, "es un enlace simbolico"
    if kind == "regular-file":
        path = tmp_path / (prefix + "archivo")
        path.write_text(TOKEN)
        return path, "no es un directorio"
    raise AssertionError(kind)


UNSAFE_KINDS = ["wrong-name", "symlink-to-dir", "dangling-symlink", "regular-file"]


def test_safe_rmtree_removes_a_safe_private_dir(lifecycle, env):
    lifecycle._safe_rmtree(env.inst)
    assert not env.token_dir.exists()


def test_safe_rmtree_treats_a_missing_directory_as_clean(lifecycle, env):
    shutil.rmtree(env.token_dir)
    lifecycle._safe_rmtree(env.inst)  # ya no existe: limpio, no lanza


def test_safe_rmtree_does_nothing_if_the_directory_was_never_created(lifecycle, env):
    env.inst.token_dir = Path()  # prepare_private_dir() nunca llego a crearlo
    lifecycle._safe_rmtree(env.inst)
    assert_credentials_intact(env)


@pytest.mark.parametrize("kind", UNSAFE_KINDS)
def test_safe_rmtree_rejects_an_existing_unsafe_path_and_removes_nothing(lifecycle, env, tmp_path, kind):
    path, fragment = make_unsafe(kind, tmp_path, env)
    env.inst.token_dir = path
    with pytest.raises(lifecycle.LifecycleError, match="NO se elimina") as info:
        lifecycle._safe_rmtree(env.inst)
    assert fragment in str(info.value)
    assert os.path.lexists(path), "la ruta rechazada debe seguir existiendo (tambien los enlaces)"
    if kind == "wrong-name":
        assert (path / "token").read_text() == TOKEN
    assert_credentials_intact(env)  # el directorio privado real (objetivo del enlace) sigue intacto


def test_safe_rmtree_rejects_a_directory_not_owned_by_the_current_user(lifecycle, env, monkeypatch):
    real_uid = os.getuid()
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.os, "getuid", lambda: real_uid + 1)
        with pytest.raises(lifecycle.LifecycleError, match="no pertenece al usuario actual"):
            lifecycle._safe_rmtree(env.inst)
    assert_credentials_intact(env)


def test_safe_rmtree_reports_every_reason_at_once(lifecycle, env, tmp_path, monkeypatch):
    path, _fragment = make_unsafe("wrong-name", tmp_path, env)
    env.inst.token_dir = path
    real_uid = os.getuid()
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.os, "getuid", lambda: real_uid + 1)
        with pytest.raises(lifecycle.LifecycleError) as info:
            lifecycle._safe_rmtree(env.inst)
    assert "el nombre no corresponde a esta ejecucion" in str(info.value)
    assert "no pertenece al usuario actual" in str(info.value)
    assert path.is_dir()


def test_safe_rmtree_does_not_treat_an_uninspectable_directory_as_clean(lifecycle, env, monkeypatch):
    def deny(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.Path, "lstat", deny)
        with pytest.raises(lifecycle.LifecycleError, match="no se pudo inspeccionar"):
            lifecycle._safe_rmtree(env.inst)
    assert_credentials_intact(env)


def patch_lstat_failing_after_the_first_call(patch, lifecycle):
    """La inspeccion previa al borrado funciona; la comprobacion posterior falla con un error que NO
    es 'no existe' (como un PermissionError)."""
    original = lifecycle.Path.lstat
    calls = []

    def flaky(self, *args, **kwargs):
        calls.append(self)
        if len(calls) == 1:
            return original(self, *args, **kwargs)
        raise PermissionError(13, "Permission denied")

    patch.setattr(lifecycle.Path, "lstat", flaky)
    return calls


def test_safe_rmtree_reports_a_deletion_failure_instead_of_hiding_it(lifecycle, env, monkeypatch):
    seen = {}

    def failing_rmtree(path, *args, **kwargs):
        seen.update(kwargs)
        raise PermissionError(13, "Permission denied")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.shutil, "rmtree", failing_rmtree)
        with pytest.raises(lifecycle.LifecycleError, match=r"no se pudo eliminar el directorio privado.*Permission denied"):
            lifecycle._safe_rmtree(env.inst)
    assert not seen.get("ignore_errors"), "el borrado no debe silenciar errores"
    assert_credentials_intact(env)


def test_safe_rmtree_accepts_a_directory_that_vanishes_during_the_removal(lifecycle, env, monkeypatch):
    real_rmtree = shutil.rmtree

    def vanishing_rmtree(path, *args, **kwargs):
        real_rmtree(path)
        raise FileNotFoundError(2, "No such file or directory")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.shutil, "rmtree", vanishing_rmtree)
        lifecycle._safe_rmtree(env.inst)  # desaparecio y se confirma con lstat: limpio
    assert not env.token_dir.exists()


def test_safe_rmtree_does_not_trust_file_not_found_if_the_directory_still_exists(lifecycle, env, monkeypatch):
    def lying_rmtree(path, *args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.shutil, "rmtree", lying_rmtree)
        with pytest.raises(lifecycle.LifecycleError, match="no se pudo eliminar el directorio privado"):
            lifecycle._safe_rmtree(env.inst)
    assert_credentials_intact(env)


def test_safe_rmtree_does_not_take_an_inspection_error_as_proof_that_the_directory_is_gone(
    lifecycle, env, monkeypatch
):
    with monkeypatch.context() as patch:
        calls = patch_lstat_failing_after_the_first_call(patch, lifecycle)
        with pytest.raises(lifecycle.LifecycleError, match="no se pudo verificar que el directorio privado"):
            lifecycle._safe_rmtree(env.inst)
    assert len(calls) >= 2  # hubo inspeccion previa y comprobacion posterior


# ---------------------------------------------------------------------------
# endpoint Docker local / remoto
# ---------------------------------------------------------------------------
LOCAL_ENDPOINTS = [
    "unix:///var/run/docker.sock",
    "unix:///run/user/1000/docker.sock",
    "unix:///Users/dev/.docker/run/docker.sock",
    "tcp://127.0.0.1:2375",
    "tcp://127.0.0.1",
    "tcp://127.0.0.5:2375",  # 127.0.0.0/8 es loopback
    "tcp://[::1]:2375",
]

# (endpoint, fragmento del motivo del rechazo)
REMOTE_ENDPOINTS = [
    ("ssh://usuario@docker.example.com", "SSH"),
    ("ssh://10.0.0.5", "SSH"),
    ("tcp://10.0.0.5:2375", "TCP remoto"),
    ("tcp://192.168.1.10:2376", "TCP remoto"),
    ("tcp://0.0.0.0:2375", "TCP remoto"),
    ("tcp://docker.example.com:2376", "TCP remoto"),
    ("tcp://localhost.evil.example:2375", "TCP remoto"),
    ("tcp://127.0.0.1.evil.example:2375", "TCP remoto"),
    ("tcp://user@127.0.0.1:2375", "credenciales"),
    ("tcp://127.0.0.1:99999", "mal formado"),
    ("tcp://:2375", "sin host"),
    ("npipe:////./pipe/docker_engine", "no admitido"),
    ("fd://", "no admitido"),
    ("http://127.0.0.1:2375", "no admitido"),
    ("unix://relative.sock", "ruta absoluta"),
    ("/var/run/docker.sock", "formato"),
]


@pytest.mark.parametrize("host", LOCAL_ENDPOINTS)
def test_local_endpoints_are_accepted(lifecycle, host):
    assert lifecycle.local_endpoint_problem(host) is None


@pytest.mark.parametrize("host,fragment", REMOTE_ENDPOINTS, ids=[case[0] for case in REMOTE_ENDPOINTS])
def test_remote_or_unverifiable_endpoints_are_rejected(lifecycle, host, fragment):
    problem = lifecycle.local_endpoint_problem(host)
    assert problem is not None and fragment in problem, problem


@pytest.mark.parametrize("host", ["tcp://localhost:2375", "tcp://LocalHost:2375"])
def test_localhost_is_accepted_only_if_it_resolves_exclusively_to_loopback(lifecycle, monkeypatch, host):
    monkeypatch.setattr(lifecycle, "_resolve_addresses", lambda _hostname: ["127.0.0.1", "::1"])
    assert lifecycle.local_endpoint_problem(host) is None


@pytest.mark.parametrize(
    "resolved",
    [["10.0.0.5"], ["127.0.0.1", "10.0.0.5"], []],
    ids=["remote-address", "mixed-loopback-and-remote", "unresolvable"],
)
def test_localhost_that_does_not_resolve_only_to_loopback_is_rejected(lifecycle, monkeypatch, resolved):
    monkeypatch.setattr(lifecycle, "_resolve_addresses", lambda _hostname: resolved)
    problem = lifecycle.local_endpoint_problem("tcp://localhost:2375")
    assert problem is not None and "localhost" in problem


def test_only_localhost_is_ever_resolved(lifecycle, monkeypatch):
    asked = []
    monkeypatch.setattr(lifecycle, "_resolve_addresses", lambda hostname: asked.append(hostname) or [])
    for host in ("tcp://127.0.0.1:2375", "tcp://10.0.0.5:2375", "tcp://docker.example.com:2376"):
        lifecycle.local_endpoint_problem(host)
    assert asked == []  # IP literales y nombres arbitrarios no se resuelven: se decide sin DNS


def test_resolve_addresses_collects_the_resolved_addresses_and_tolerates_errors(lifecycle, monkeypatch):
    def fake_getaddrinfo(hostname, port, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 0)), (10, 1, 6, "", ("::1", 0, 0, 0)), (2, 1, 6, "", ("127.0.0.1", 0))]

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.socket, "getaddrinfo", fake_getaddrinfo)
        assert lifecycle._resolve_addresses("localhost") == ["127.0.0.1", "::1"]

    def failing_getaddrinfo(*args, **kwargs):
        raise OSError("no se puede resolver")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.socket, "getaddrinfo", failing_getaddrinfo)
        assert lifecycle._resolve_addresses("localhost") == []


@pytest.mark.parametrize("host", LOCAL_ENDPOINTS)
def test_capture_accepts_a_local_endpoint(lifecycle, env, host):
    fake = env.build()
    fake.context_host = host
    assert lifecycle.capture_docker_target() == lifecycle.DockerTarget("default", host)


def test_capture_accepts_localhost_when_it_is_verified_as_loopback(lifecycle, env, monkeypatch):
    monkeypatch.setattr(lifecycle, "_resolve_addresses", lambda _hostname: ["127.0.0.1"])
    fake = env.build()
    fake.context_host = "tcp://localhost:2375"
    assert lifecycle.capture_docker_target().host == "tcp://localhost:2375"


@pytest.mark.parametrize("host,fragment", REMOTE_ENDPOINTS, ids=[case[0] for case in REMOTE_ENDPOINTS])
def test_capture_rejects_remote_or_unverifiable_endpoints(lifecycle, env, host, fragment):
    fake = env.build()
    fake.context_host = host
    with pytest.raises(lifecycle.LifecycleError, match="no es local") as info:
        lifecycle.capture_docker_target()
    assert fragment in str(info.value)


@pytest.mark.parametrize("host,fragment", REMOTE_ENDPOINTS, ids=[case[0] for case in REMOTE_ENDPOINTS])
def test_start_container_creates_nothing_for_a_remote_endpoint(lifecycle, env, host, fragment):
    env.inst.docker_target = None
    env.inst.daemon_id = None
    env.inst.container_id = None
    env.inst.run_attempted = False
    fake = env.build()
    fake.context_host = host
    with pytest.raises(lifecycle.LifecycleError, match="no es local"):
        lifecycle.start_container(env.inst, "postgres:16")
    assert fake.verbs == [] and fake.info_calls == 0  # ni `docker run` ni siquiera la consulta del ID
    assert env.inst.run_attempted is False and env.inst.docker_target is None and env.inst.daemon_id is None


def test_a_remote_docker_host_is_rejected_even_if_it_matches_the_captured_endpoint(lifecycle, env, monkeypatch):
    # DOCKER_HOST coincide con el endpoint capturado (se "demostraria"), pero no es local.
    fake = build_with_docker_host(env, monkeypatch, "tcp://10.0.0.5:2375", context_host="tcp://10.0.0.5:2375")
    with pytest.raises(lifecycle.LifecycleError, match="no es local"):
        lifecycle.capture_docker_target()
    assert fake.verbs == []


# ---------------------------------------------------------------------------
# ID del Docker Engine
# ---------------------------------------------------------------------------
def test_capture_daemon_id_reads_the_id_pinned_to_the_context(lifecycle, env):
    fake = env.build()
    assert lifecycle.capture_daemon_id(env.inst.docker_target) == DAEMON_ID
    assert fake.calls == [("info", "--format", "{{.ID}}")]
    assert fake.targets == [("info", env.inst.docker_target)]


@pytest.mark.parametrize("problem", ["empty", "garbage", "error", "unreachable"])
def test_capture_daemon_id_fails_closed_without_a_valid_id(lifecycle, env, problem):
    env.build(daemon_plan=[problem])
    with pytest.raises(lifecycle.LifecycleError, match="ID valido del Docker Engine"):
        lifecycle.capture_daemon_id(env.inst.docker_target)


@pytest.mark.parametrize("problem", ["empty", "garbage", "error", "unreachable"])
def test_start_container_creates_nothing_if_the_daemon_id_cannot_be_obtained(lifecycle, env, problem):
    env.inst.docker_target = None
    env.inst.daemon_id = None
    env.inst.container_id = None
    env.inst.run_attempted = False
    fake = env.build(daemon_plan=[problem])
    with pytest.raises(lifecycle.LifecycleError, match="ID valido del Docker Engine"):
        lifecycle.start_container(env.inst, "postgres:16")
    assert fake.verbs == []  # no se llego a `docker run`
    # La instancia no queda con valores parciales: nada registrado y nada intentado.
    assert env.inst.run_attempted is False and env.inst.docker_target is None and env.inst.daemon_id is None


@pytest.mark.parametrize("problem", DAEMON_PROBLEMS)
def test_lookup_is_unknown_if_the_docker_engine_id_changed_or_cannot_be_verified(lifecycle, env, problem):
    fake = env.build(daemon_plan=[problem])
    assert lifecycle.lookup_container(env.inst) == ("unknown", None)
    assert fake.verbs == []  # no se pregunta por el contenedor a un daemon que quiza no es el mismo
    assert fake.context_checks == 1 and fake.info_calls == 1


def test_lookup_is_unknown_without_a_recorded_daemon_id(lifecycle, env):
    env.inst.daemon_id = None
    fake = env.build()
    assert lifecycle.lookup_container(env.inst) == ("unknown", None)
    assert fake.calls == []


@pytest.mark.parametrize("problem", DAEMON_PROBLEMS)
def test_destroy_with_a_different_or_unverifiable_docker_engine_touches_nothing(lifecycle, env, problem):
    fake = env.build(daemon_plan=[problem])
    with pytest.raises(lifecycle.LifecycleError, match="no se pudo verificar el estado del contenedor"):
        lifecycle.destroy(env.inst)
    assert fake.verbs == []
    assert_credentials_intact(env)


# ---------------------------------------------------------------------------
# teardown
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "config",
    [
        dict(exists=False),
        dict(exists=True, running=False),
        dict(exists=True, running=True, sessions="0\n"),
    ],
    ids=["absent", "present-stopped", "present-running-without-sessions"],
)
def test_teardown_succeeds_only_when_the_container_is_confirmed_gone(lifecycle, env, capsys, config):
    fake = env.build(**config)
    assert lifecycle.teardown(env.inst) is True
    assert not env.token_dir.exists()
    assert "TEARDOWN NO COMPLETADO" not in capsys.readouterr().out
    assert ("rm" in fake.verbs) is config["exists"]
    assert fake.context_checks >= 1
    assert_all_pinned(fake, env.inst)  # incluidas las consultas de sesiones (`exec`) y `inspect`


# (id, configuracion del doble, fragmento del motivo, `docker rm` debio invocarse)
KEPT_CASES = [
    ("docker-unreachable", dict(ps_plan=["unreachable"]), "estado incierto", False),
    ("docker-daemon-error", dict(ps_plan=["daemon_error"]), "estado incierto", False),
    ("unexpected-ps-output", dict(ps_plan=["garbage"]), "estado incierto", False),
    ("multiple-ids", dict(ps_plan=["two_ids"]), "estado incierto", False),
    ("different-id", dict(ps_plan=["other_id"]), "estado incierto", False),
    ("running-state-unverifiable", dict(running_inspect="error"), "estado incierto", False),
    ("labels-unverifiable", dict(labels="error"), "teardown no confirmado", False),
    ("foreign-container", dict(labels="foreign"), "teardown no confirmado", False),
    ("docker-rm-fails", dict(rm="fail"), "teardown no confirmado", True),
    ("present-after-rm", dict(rm="noop"), "no se pudo confirmar la eliminacion", True),
    ("state-after-rm-unverifiable", dict(ps_plan=["state", "state", "unreachable"]),
     "no se pudo confirmar la eliminacion", True),
]
# Contexto/endpoint de Docker no verificable, renombrado, con endpoint distinto o que cambia a mitad
# del teardown: el estado se trata como DESCONOCIDO y se conserva todo.
KEPT_CASES += [
    (f"context-{problem}", dict(context_plan=[problem]), "contexto/endpoint/ID del Docker Engine registrados", False)
    for problem in CONTEXT_PROBLEMS
]
KEPT_CASES += [
    ("context-changes-before-destroy", dict(context_plan=["ok", "endpoint_changed"]),
     "teardown no confirmado", False),
    ("context-changes-after-rm", dict(context_plan=["ok", "ok", "endpoint_changed"]),
     "no se pudo confirmar la eliminacion", True),
]
# Mismo contexto y endpoint pero OTRO Docker Engine (ID distinto) o ID no verificable: estado desconocido.
KEPT_CASES += [
    (f"daemon-{problem}", dict(daemon_plan=[problem]), "contexto/endpoint/ID del Docker Engine registrados", False)
    for problem in DAEMON_PROBLEMS
]
KEPT_CASES += [
    ("daemon-changes-before-destroy", dict(daemon_plan=["ok", "other"]), "teardown no confirmado", False),
    ("daemon-changes-after-rm", dict(daemon_plan=["ok", "ok", "other"]),
     "no se pudo confirmar la eliminacion", True),
]


@pytest.mark.parametrize(
    "config,reason,rm_called",
    [case[1:] for case in KEPT_CASES],
    ids=[case[0] for case in KEPT_CASES],
)
def test_teardown_with_an_uncertain_or_failed_state_keeps_credentials_and_explains_recovery(
    lifecycle, env, capsys, config, reason, rm_called
):
    fake = env.build(**config)
    assert lifecycle.teardown(env.inst) is False  # nunca se declara exitoso
    assert_credentials_intact(env)  # las credenciales no se tocan
    output = capsys.readouterr().out
    assert_recovery_info(env, output)  # y se informa como recuperar el contenedor (mismo contexto)
    assert "contexto Docker registrado: default (unix:///var/run/docker.sock)" in output, output
    assert reason in output, output
    assert ("rm" in fake.verbs) is rm_called


@pytest.mark.parametrize("exists", [False, True], ids=["container-absent", "container-removed"])
def test_teardown_failure_to_remove_the_private_dir_is_not_success(lifecycle, env, monkeypatch, capsys, exists):
    fake = env.build(exists=exists)
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.shutil, "rmtree", lambda *args, **kwargs: None)
        assert lifecycle.teardown(env.inst) is False
    assert_credentials_intact(env)
    output = capsys.readouterr().out
    assert_recovery_info(env, output)
    assert "no se pudo eliminar el directorio privado" in output
    assert ("rm" in fake.verbs) is exists


def test_teardown_is_not_success_if_the_private_dir_deletion_fails(lifecycle, env, monkeypatch, capsys):
    env.build(exists=False)

    def failing_rmtree(path, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle.shutil, "rmtree", failing_rmtree)
        assert lifecycle.teardown(env.inst) is False
    assert_credentials_intact(env)
    output = capsys.readouterr().out
    assert_recovery_info(env, output)
    assert "no se pudo eliminar el directorio privado" in output and "Permission denied" in output


def test_teardown_is_not_success_if_the_cleanup_cannot_be_verified(lifecycle, env, monkeypatch, capsys):
    env.build(exists=False)
    with monkeypatch.context() as patch:
        patch_lstat_failing_after_the_first_call(patch, lifecycle)
        assert lifecycle.teardown(env.inst) is False  # no se puede probar que desaparecio: sin exito
    output = capsys.readouterr().out
    assert_recovery_info(env, output)
    assert "no se pudo verificar que el directorio privado" in output


def test_teardown_without_a_recorded_context_keeps_credentials_and_does_not_invent_one(lifecycle, env, capsys):
    env.inst.docker_target = None  # se intento crear el contenedor pero el contexto nunca se registro
    env.inst.daemon_id = None
    fake = env.build()
    assert lifecycle.teardown(env.inst) is False
    assert fake.calls == []  # sin contexto registrado no se le pregunta nada a ningun daemon
    assert_credentials_intact(env)
    output = capsys.readouterr().out
    assert_recovery_info(env, output, docker_cmd="docker", daemon_id=None)
    assert "ID del Docker Engine registrado" not in output
    assert "contexto Docker: no registrado" in output
    assert "--context" not in output


@pytest.mark.parametrize("kind", UNSAFE_KINDS)
@pytest.mark.parametrize("exists", [False, True], ids=["container-absent", "container-removed"])
def test_teardown_with_an_unsafe_private_dir_is_not_success_and_reports_the_reason(
    lifecycle, env, tmp_path, capsys, kind, exists
):
    path, fragment = make_unsafe(kind, tmp_path, env)
    env.inst.token_dir = path
    fake = env.build(exists=exists)
    assert lifecycle.teardown(env.inst) is False  # nunca se declara exitoso
    assert os.path.lexists(path)  # la ruta rechazada se conserva
    assert_credentials_intact(env)
    output = capsys.readouterr().out
    assert_recovery_info(env, output)  # y se informa como recuperar
    assert fragment in output and "NO se elimina" in output  # con el MOTIVO
    assert ("rm" in fake.verbs) is exists


def test_teardown_treats_an_already_removed_private_dir_as_clean(lifecycle, env, capsys):
    shutil.rmtree(env.token_dir)
    env.build(exists=False)
    assert lifecycle.teardown(env.inst) is True
    assert "TEARDOWN NO COMPLETADO" not in capsys.readouterr().out
