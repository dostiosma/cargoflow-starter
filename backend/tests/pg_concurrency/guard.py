"""Guardas de seguridad de la infraestructura de pruebas PostgreSQL.

Solo usa la biblioteca estandar a proposito: lo importan tanto los tests (via
paquete) como infrastructure/test-db/pg_test_db.py (por ruta de archivo), de modo
que la validacion de la URL y del sentinel tiene UNA sola implementacion.

Principios:
  * TEST_DATABASE_URL es la unica fuente. DATABASE_URL nunca se lee ni sirve de
    respaldo.
  * Formato estricto (fullmatch): host exactamente 127.0.0.1, base y rol con el
    patron que genera el aprovisionador, sin query string. Cualquier otra cosa se
    rechaza; no se intenta "arreglar" la URL.
  * Los mensajes de error nunca incluyen la URL, el password ni el token.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

ALLOWED_HOST = "127.0.0.1"
MIN_PORT = 1024
MAX_PORT = 65535
TOKEN_MAX_BYTES = 128
DIRTY_MARKER_NAME = "dirty"
URL_FORMAT = (
    "postgresql+psycopg2://cf_test_user_<hex16>:<password-hex>@127.0.0.1:<puerto>/cf_test_<hex16>"
)

_URL_RE = re.compile(
    r"postgresql\+psycopg2://"
    r"(?P<user>cf_test_user_(?P<user_run>[0-9a-f]{16})):"
    r"(?P<password>[0-9a-f]{32,128})@"
    r"(?P<host>[^:/@?#]+):(?P<port>[0-9]{1,5})/"
    r"(?P<db>cf_test_(?P<db_run>[0-9a-f]{16}))"
)
_TOKEN_RE = re.compile(r"[0-9a-f]{64}")

SQL_IDENTITY = "SELECT current_database(), current_user"
SQL_ROLE = (
    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
    "FROM pg_roles WHERE rolname = current_user"
)
SQL_SENTINEL = "SELECT db_name, run_id, token_sha256 FROM cf_test_sentinel WHERE id = 1"


class GuardError(Exception):
    """La configuracion de pruebas no es segura o no es valida."""


@dataclass(frozen=True, repr=False)
class ValidatedTarget:
    url: str  # contiene el password: nunca se imprime (ver __repr__/__str__)
    host: str
    port: int
    database: str
    user: str
    run_id: str

    def redacted(self) -> str:
        return f"postgresql+psycopg2://{self.user}:***@{self.host}:{self.port}/{self.database}"

    def __repr__(self) -> str:
        return f"ValidatedTarget({self.redacted()})"

    __str__ = redacted


def validate_test_database_url(raw: object) -> ValidatedTarget:
    if not isinstance(raw, str) or not raw:
        raise GuardError("TEST_DATABASE_URL esta vacia")
    match = _URL_RE.fullmatch(raw)
    if match is None:
        raise GuardError(
            "TEST_DATABASE_URL no cumple el formato exigido "
            f"({URL_FORMAT}); no se admiten query strings, otros drivers ni otros nombres"
        )
    if match["host"] != ALLOWED_HOST:
        raise GuardError(
            "el host de TEST_DATABASE_URL debe ser exactamente 127.0.0.1 "
            "(ni localhost, ni ::1, ni un socket)"
        )
    port = int(match["port"])
    if not MIN_PORT <= port <= MAX_PORT:
        raise GuardError(f"el puerto de TEST_DATABASE_URL debe estar entre {MIN_PORT} y {MAX_PORT}")
    if match["user_run"] != match["db_run"]:
        raise GuardError("el rol y la base de TEST_DATABASE_URL pertenecen a ejecuciones distintas")
    return ValidatedTarget(
        url=raw,
        host=match["host"],
        port=port,
        database=match["db"],
        user=match["user"],
        run_id=match["db_run"],
    )


def load_target_from_env(environ: Mapping[str, str] | None = None) -> ValidatedTarget:
    """Lee EXCLUSIVAMENTE TEST_DATABASE_URL. No existe respaldo a DATABASE_URL."""
    env = os.environ if environ is None else environ
    raw = env.get("TEST_DATABASE_URL")
    if not raw:
        raise GuardError(
            "TEST_DATABASE_URL no esta definida; no se usa DATABASE_URL como respaldo. "
            "Ejecute las pruebas con infrastructure/test-db/pg_test_db.py"
        )
    return validate_test_database_url(raw)


def read_token_file(path: str) -> str:
    """Lee el token del entorno desechable sin la secuencia insegura comprobar-y-abrir.

    Se abre UNA vez, con O_NOFOLLOW y O_CLOEXEC (cuando existen) y todas las
    validaciones se hacen con fstat() sobre el descriptor ya abierto: regular,
    del mismo usuario, sin permisos para grupo/otros, un solo enlace duro y de
    tamano acotado. O_NONBLOCK evita quedarse colgado si la ruta fuera un FIFO.
    No se llama a stat()/lstat()/exists()/islink() sobre la ruta.
    """
    flags = os.O_RDONLY
    for name in ("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK", "O_NOCTTY"):
        flags |= getattr(os, name, 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise GuardError(
            "no se pudo abrir de forma segura el archivo de token "
            f"({exc.strerror or type(exc).__name__}); un enlace simbolico se rechaza"
        ) from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise GuardError("el token debe ser un archivo regular")
        geteuid = getattr(os, "geteuid", None)
        if geteuid is not None and info.st_uid != geteuid():
            raise GuardError("el archivo de token no pertenece al usuario actual")
        if info.st_mode & 0o077:
            raise GuardError("el archivo de token debe tener permisos 0600 (sin acceso de grupo/otros)")
        if info.st_nlink != 1:
            raise GuardError("el archivo de token no puede tener enlaces duros adicionales")
        if not 0 < info.st_size <= TOKEN_MAX_BYTES:
            raise GuardError("el archivo de token esta vacio o excede el tamano maximo")
        data = b""
        while len(data) < info.st_size:
            chunk = os.read(fd, info.st_size - len(data))
            if not chunk:
                break
            data += chunk
        if len(data) != info.st_size:
            raise GuardError("lectura incompleta del archivo de token")
    finally:
        os.close(fd)
    try:
        token = data.decode("ascii").strip()
    except UnicodeDecodeError:
        raise GuardError("el token debe ser ASCII") from None
    if _TOKEN_RE.fullmatch(token) is None:
        raise GuardError("el token no tiene el formato esperado (64 caracteres hexadecimales)")
    return token


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


FetchRows = Callable[[str], Sequence[Sequence[object]]]


def verify_sentinel(fetch: FetchRows, target: ValidatedTarget, token: str) -> None:
    """Exige que la base conectada sea la que el aprovisionador creo para ESTA ejecucion.

    `fetch(sql)` ejecuta una consulta de solo lectura y devuelve filas. Se llama
    antes de cualquier operacion destructiva (create_all, TRUNCATE). Comprueba:
      1. base y usuario actuales == los de la URL validada;
      2. el rol no es superusuario ni tiene CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS;
      3. existe cf_test_sentinel con la misma base, el mismo run_id y el sha256 del
         token leido del archivo (comparacion en tiempo constante).
    """
    try:
        identity = fetch(SQL_IDENTITY)
        role = fetch(SQL_ROLE)
        sentinel = fetch(SQL_SENTINEL)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo debe cerrar la puerta
        raise GuardError(
            f"no se pudo leer el sentinel de la base de pruebas ({type(exc).__name__}); "
            "se rechazan las operaciones destructivas"
        ) from None

    if len(identity) != 1 or tuple(identity[0]) != (target.database, target.user):
        raise GuardError("la conexion no apunta a la base/rol de TEST_DATABASE_URL")
    if len(role) != 1 or any(bool(flag) for flag in role[0]):
        raise GuardError("el rol de pruebas tiene privilegios que no debe tener")
    if len(sentinel) != 1:
        raise GuardError("sentinel ausente o duplicado en la base de pruebas")
    db_name, run_id, stored_hash = sentinel[0]
    if db_name != target.database or run_id != target.run_id:
        raise GuardError("el sentinel no corresponde a esta base/ejecucion")
    if not hmac.compare_digest(str(stored_hash), token_sha256(token)):
        raise GuardError("el token no coincide con el sentinel de la base")


def mark_dirty(token_file: str, reason: str) -> None:
    """Deja un marcador junto al token para que el teardown conserve el contenedor."""
    directory = os.path.dirname(os.path.abspath(token_file))
    path = os.path.join(directory, DIRTY_MARKER_NAME)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, (reason.strip() + "\n").encode("utf-8", "replace")[:2000])
    finally:
        os.close(fd)
