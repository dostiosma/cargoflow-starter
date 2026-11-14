"""Pruebas unitarias de las guardas (sin base de datos ni Docker).

Marcador `pg_concurrency_unit`: opt-in, igual que el resto del paquete. Las ejecuta
pg_test_db.py ANTES de crear ningun contenedor.
"""
import os
import stat

import pytest

from . import guard

pytestmark = pytest.mark.pg_concurrency_unit

RUN = "0123456789abcdef"
PASSWORD = "ab" * 24
GOOD_URL = f"postgresql+psycopg2://cf_test_user_{RUN}:{PASSWORD}@127.0.0.1:54321/cf_test_{RUN}"
TOKEN = "cd" * 32


def _write(path, content, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(fd, content if isinstance(content, bytes) else content.encode())
    finally:
        os.close(fd)
    os.chmod(path, mode)
    return str(path)


# -- URL -------------------------------------------------------------------
def test_valid_url_is_accepted_and_never_printed():
    target = guard.validate_test_database_url(GOOD_URL)
    assert (target.host, target.port, target.database, target.run_id) == (
        "127.0.0.1", 54321, f"cf_test_{RUN}", RUN,
    )
    for rendering in (repr(target), str(target), target.redacted()):
        assert PASSWORD not in rendering and "***" in rendering


@pytest.mark.parametrize(
    "mutator",
    [
        lambda u: u.replace("127.0.0.1", "localhost"),
        lambda u: u.replace("127.0.0.1", "[::1]"),
        lambda u: u.replace("127.0.0.1", "0.0.0.0"),
        lambda u: u.replace("127.0.0.1", "127.0.0.1.evil.example"),
        lambda u: u.replace(f"/cf_test_{RUN}", "/cargoflow"),
        lambda u: u.replace(f"cf_test_user_{RUN}", "cargoflow"),
        lambda u: u.replace(f"cf_test_user_{RUN}", "cf_test_user_" + "f" * 16),  # otra ejecucion
        lambda u: u.replace(":54321", ":80"),
        lambda u: u.replace(":54321", ":70000"),
        lambda u: u + "?host=/var/run/postgresql",
        lambda u: u + "\n",
        lambda u: u.replace("postgresql+psycopg2", "postgresql"),
        lambda u: u.replace(PASSWORD, "corta"),
        lambda u: "",
    ],
)
def test_invalid_urls_are_rejected(mutator):
    with pytest.raises(guard.GuardError) as info:
        guard.validate_test_database_url(mutator(GOOD_URL))
    assert PASSWORD not in str(info.value)


def test_no_fallback_to_database_url():
    env = {"DATABASE_URL": GOOD_URL}  # una URL "valida" en DATABASE_URL NO debe usarse
    with pytest.raises(guard.GuardError) as info:
        guard.load_target_from_env(env)
    assert "TEST_DATABASE_URL" in str(info.value)
    assert guard.load_target_from_env({"TEST_DATABASE_URL": GOOD_URL}).database == f"cf_test_{RUN}"


# -- token -------------------------------------------------------------------
def test_token_is_read_with_nofollow_cloexec_and_without_path_prechecks(tmp_path, monkeypatch):
    path = _write(tmp_path / "token", TOKEN + "\n")
    seen = {}
    real_open = os.open

    def spy(p, flags, *args, **kwargs):
        seen["flags"] = flags
        return real_open(p, flags, *args, **kwargs)

    def forbidden(*_a, **_k):
        raise AssertionError("no se debe consultar la ruta antes de abrirla")

    with monkeypatch.context() as m:
        m.setattr(guard.os, "open", spy)
        m.setattr(guard.os, "stat", forbidden)
        m.setattr(guard.os, "lstat", forbidden)
        assert guard.read_token_file(path) == TOKEN
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        if hasattr(os, name):
            assert seen["flags"] & getattr(os, name), name


def test_token_rejects_symlink(tmp_path):
    if not hasattr(os, "symlink") or not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("sin symlinks / O_NOFOLLOW en esta plataforma")
    target = _write(tmp_path / "real", TOKEN)
    link = tmp_path / "link"
    os.symlink(target, link)
    with pytest.raises(guard.GuardError):
        guard.read_token_file(str(link))


@pytest.mark.parametrize(
    "content,mode",
    [
        (TOKEN, 0o644),            # visible para grupo/otros
        (TOKEN, 0o640),
        ("", 0o600),               # vacio
        ("z" * 64, 0o600),         # no hexadecimal
        ("ab" * 16, 0o600),        # corto
        (TOKEN + "x" * 200, 0o600),  # excede el tamano maximo
        (b"\xff\xfe" + b"a" * 62, 0o600),  # no ASCII
    ],
)
def test_token_rejects_bad_files(tmp_path, content, mode):
    path = _write(tmp_path / "bad", content, mode)
    with pytest.raises(guard.GuardError) as info:
        guard.read_token_file(path)
    assert TOKEN not in str(info.value)


def test_token_rejects_directory_and_hardlink(tmp_path):
    with pytest.raises(guard.GuardError):
        guard.read_token_file(str(tmp_path))
    original = _write(tmp_path / "t", TOKEN)
    os.link(original, tmp_path / "t2")
    with pytest.raises(guard.GuardError):
        guard.read_token_file(original)


def test_token_missing_file_is_rejected(tmp_path):
    with pytest.raises(guard.GuardError):
        guard.read_token_file(str(tmp_path / "nope"))


# -- sentinel ----------------------------------------------------------------
def _fetch(identity=None, role=None, sentinel=None, boom=False):
    target_identity = identity if identity is not None else [(f"cf_test_{RUN}", f"cf_test_user_{RUN}")]
    target_role = role if role is not None else [(False, False, False, False, False)]
    target_sentinel = (
        sentinel if sentinel is not None else [(f"cf_test_{RUN}", RUN, guard.token_sha256(TOKEN))]
    )

    def fetch(sql):
        if boom:
            raise RuntimeError("relation does not exist")
        if sql == guard.SQL_IDENTITY:
            return target_identity
        if sql == guard.SQL_ROLE:
            return target_role
        if sql == guard.SQL_SENTINEL:
            return target_sentinel
        raise AssertionError(sql)

    return fetch


def test_sentinel_accepts_the_matching_environment():
    guard.verify_sentinel(_fetch(), guard.validate_test_database_url(GOOD_URL), TOKEN)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"identity": [("cargoflow", f"cf_test_user_{RUN}")]},
        {"identity": [(f"cf_test_{RUN}", "postgres")]},
        {"role": [(True, False, False, False, False)]},      # superusuario
        {"role": [(False, True, False, False, False)]},      # CREATEDB
        {"role": [(False, False, False, False, True)]},      # BYPASSRLS
        {"sentinel": []},                                    # sentinel ausente
        {"sentinel": [(f"cf_test_{RUN}", "f" * 16, guard.token_sha256(TOKEN))]},  # otra ejecucion
        {"sentinel": [("otra_db", RUN, guard.token_sha256(TOKEN))]},
        {"sentinel": [(f"cf_test_{RUN}", RUN, guard.token_sha256("00" * 32))]},   # token ajeno
        {"boom": True},                                      # tabla inexistente
    ],
)
def test_sentinel_rejects_everything_else(kwargs):
    with pytest.raises(guard.GuardError) as info:
        guard.verify_sentinel(_fetch(**kwargs), guard.validate_test_database_url(GOOD_URL), TOKEN)
    assert TOKEN not in str(info.value) and guard.token_sha256(TOKEN) not in str(info.value)


# -- marcador de contaminacion -----------------------------------------------
def test_dirty_marker_is_private_and_next_to_the_token(tmp_path):
    token_file = _write(tmp_path / "token", TOKEN)
    guard.mark_dirty(token_file, "hilos vivos")
    marker = tmp_path / guard.DIRTY_MARKER_NAME
    assert marker.read_text().strip() == "hilos vivos"
    if os.name == "posix":
        assert stat.S_IMODE(marker.stat().st_mode) == 0o600
