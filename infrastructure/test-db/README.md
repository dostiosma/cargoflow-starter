# PostgreSQL desechable para las pruebas de concurrencia

Soporta las pruebas T3-C, T3-D, T3-D-b y T3-E de `POST /api/shipments/{id}/assign` y sus
mutaciones M1-V, M1-D, M2 y M3 (`backend/tests/pg_concurrency/`). **No toca la base de
desarrollo ni `docker-compose.yml`.** Estas pruebas son opt-in: el `pytest` normal las excluye.

## Uso

Desde la raíz del repo, con el entorno virtual del backend activo y Docker disponible:

```bash
python infrastructure/test-db/pg_test_db.py check        # verificaciones previas, sin efectos
python infrastructure/test-db/pg_test_db.py suite        # unitarias -> contenedor -> suite -> teardown
python infrastructure/test-db/pg_test_db.py mutations    # unitarias -> contenedor -> línea base + M1-V/M1-D/M2/M3
python infrastructure/test-db/pg_test_db.py mutations --only M2 M3
python infrastructure/test-db/pg_test_db.py list         # contenedores de pruebas (solo lectura)
```

Códigos de salida: `0` todo correcto · `1` pruebas/mutaciones no cumplen · `2` error del ciclo de
vida · `3` todo pasó pero el teardown no se completó y se conservó el contenedor y/o el directorio
privado (ver «Recuperación»).
`CARGOFLOW_PG_STRESS_ITERATIONS` (por defecto 20) fija las iteraciones de las pruebas de carrera.
`CARGOFLOW_PGTEST_IMAGE` (por defecto `postgres:16`, la misma mayor que `docker-compose.yml`) cambia la imagen.

## Modelo de seguridad

| Requisito | Cómo se cumple |
|---|---|
| Nunca la base de desarrollo/producción | Contenedor propio (`cf-pgtest-<run>`), base `cf_test_<run>` y rol `cf_test_user_<run>` por ejecución. |
| Sin `DATABASE_URL` como respaldo | Los tests leen **solo** `TEST_DATABASE_URL`; en el proceso hijo `DATABASE_URL` apunta a `127.0.0.1:1` (fallaría si algo lo usara) y se eliminan las variables `PG*`. |
| Solo loopback | `-p 127.0.0.1::5432` (puerto efímero); se verifica con `docker port` y la URL exige el host exacto `127.0.0.1`. |
| Credenciales temporales y sin logs | Contraseñas y token aleatorios; viajan por entorno, stdin o archivo 0600, nunca por argv; todo lo impreso pasa por un redactor. |
| Rol de mínimos privilegios | `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, dueño solo de su base, `CONNECTION LIMIT 20`; la guarda lo comprueba en `pg_roles`. |
| Sentinel antes de lo destructivo | `public.cf_test_sentinel` guarda base, `run_id` y `sha256(token)`; `create_all` y `TRUNCATE` re-verifican identidad, rol y token (`hmac.compare_digest`). El rol de pruebas solo puede leerla. |
| Lectura segura del token | `os.open` con `O_NOFOLLOW`/`O_CLOEXEC`/`O_NONBLOCK` y validación con `fstat()` sobre el descriptor (regular, mismo usuario, 0600, un enlace, tamaño acotado). Sin comprobación de ruta previa. |
| Teardown solo de lo propio | Se destruye únicamente el contenedor cuyo id, etiquetas y `owner_pid` coinciden con este proceso; el directorio del token solo se borra **cuando el contenedor está confirmado como eliminado o inexistente**. Si el directorio privado ya no existe, se considera limpio. Si existe pero no cumple las condiciones de seguridad (nombre de esta ejecución, directorio real y no enlace simbólico, propiedad del usuario actual; se inspecciona con `lstat`, sin seguir enlaces) o no puede inspeccionarse, `_safe_rmtree` lanza `LifecycleError`: no se borra nada, el teardown no se declara exitoso, el directorio se conserva y se informa el motivo. El borrado no oculta errores (`shutil.rmtree` sin `ignore_errors`) y la confirmación posterior usa `lstat`: solo «no existe» prueba que desapareció; si el borrado falla o la existencia no puede comprobarse, la operación falla explícitamente y el teardown no informa éxito. |
| Estado incierto ≠ inexistente | Se consulta a Docker por el nombre del contenedor. «Inexistente» solo se acepta si Docker responde con éxito y no lo encuentra. Ante un error (daemon caído, timeout, salida inesperada) el estado es *incierto*: no se elimina nada, se conservan contenedor y directorio privado (credenciales) y el teardown **no** se declara exitoso. |
| Contexto Docker fijado | **Si `DOCKER_HOST` está definido, solo se continúa cuando se demuestra que el contexto capturado es ese destino: contexto `default` y endpoint idéntico, cadena a cadena, al valor de `DOCKER_HOST` (también se rechaza vacío o sin normalizar, p. ej. `tcp://host` sin puerto). Si no, el script falla cerrado antes de crear el contenedor y de aprovisionar nada.** Al crear el contenedor se registra el contexto y el endpoint efectivos (`docker context inspect`). Todas las operaciones posteriores (`run`, `port`, `exec`, `inspect`, `ps`, `rm`) se lanzan con `docker --context <ctx>`, que tiene prioridad sobre `DOCKER_HOST`/`DOCKER_CONTEXT` y sobre el contexto activo. Antes de cada búsqueda del contenedor se verifica que ese contexto exista y apunte al mismo endpoint; si no se puede verificar o cambió (renombrado, endpoint distinto, borrado o nunca registrado) el estado es **desconocido**: ni siquiera se consulta al daemon, se conservan contenedor y credenciales y el teardown **no** se declara exitoso. |
| Solo Docker local | El laboratorio publica PostgreSQL en `127.0.0.1` y `TEST_DATABASE_URL` usa `127.0.0.1`, por lo que el puerto publicado solo es alcanzable si el daemon corre en el **mismo entorno** que pytest. Se acepta únicamente `unix:///ruta/absoluta` (socket Unix local) y `tcp://` hacia loopback verificado: IP literal de loopback (`127.0.0.0/8`, `::1`) o `localhost` si resuelve exclusivamente a loopback. Se rechazan (fallo cerrado, antes de crear nada) `ssh://`, `tcp://` remoto o con un nombre no verificable, `npipe://`, `fd://`, otros esquemas y credenciales en la URL. No se implementan túneles ni Docker remoto. |
| Identidad del daemon | Además del contexto y el endpoint, al crear el contenedor se registra el **ID del Docker Engine** (`docker --context <ctx> info --format '{{.ID}}'`) y debe tener un formato válido; si no se obtiene, no se crea nada. Antes de cada búsqueda del contenedor se vuelve a leer y debe coincidir: un contexto que pase a apuntar a otro daemon, un ID ilegible o ausente dejan el estado **desconocido** (se conserva todo y el informe incluye el ID registrado). |
| Sin hilos ni sesiones vivas | Compuertas liberadas en `finally`; los hilos de petición se esperan con `join(timeout)` y se comprueba explícitamente que no sigan vivos (`done` no equivale a «el hilo terminó»); `idle_in_transaction_session_timeout`/`lock_timeout` en la propia base. Si queda un hilo, una sesión activa o una conexión del pool sin devolver (`app_engine.pool.checkedout()`, comprobado **antes** de `dispose()`), se escribe un marcador y **no** se elimina el contenedor. Los fallos del arnés llevan el código `[CF-LEAK]`. |

## Recuperación

Si el script informa «TEARDOWN NO COMPLETADO» (sesiones activas, marcador de contaminación o estado
incierto del contenedor, incluido un contexto/endpoint de Docker no verificable o cambiado), indica el
motivo, el nombre, el puerto, **el contexto Docker registrado** y el directorio privado, que se
conserva porque contiene el token. Use el **mismo contexto** que registró el script (los comandos
impresos ya lo incluyen): compruebe primero el estado real con
`docker --context <ctx> ps -a --filter 'name=^/<nombre>$'` y, si procede, inspeccione
(`docker --context <ctx> logs`, `pg_stat_activity`). Al terminar:
`docker --context <ctx> rm -f -v <nombre> && rm -rf <directorio>`. Si el contexto nunca llegó a
registrarse, los comandos se imprimen con `docker` a secas y el informe lo indica. El informe incluye
también el **ID del Docker Engine** registrado: compruebe con `docker --context <ctx> info` que sigue
siendo el mismo daemon antes de eliminar nada. Si el motivo es un **directorio privado rechazado por
seguridad** (enlace simbólico, no es un directorio, otro propietario), inspecciónelo antes de ejecutar
`rm -rf`: puede no ser el directorio que creó el script.

## Qué hace cada archivo

- `pg_test_db.py`: ciclo de vida (contenedor, aprovisionamiento, sentinel, ejecución, teardown).
- `../../backend/tests/pg_concurrency/guard.py`: validación de URL, lectura del token y verificación del sentinel (solo stdlib; lo importan el script y los tests).
- `../../backend/tests/pg_concurrency/test_lifecycle_unit.py`: pruebas unitarias de `lookup_container`, `destroy` y `teardown` con un **doble** del comando `docker` (sin Docker real): contenedor ausente, presente, Docker inaccesible, `docker rm` fallido, contenedor aún presente tras `docker rm`, fallo al borrar el directorio privado y contexto/endpoint de Docker no verificable, renombrado, modificado a mitad del teardown o sin registrar (además de comprobar que todas las operaciones se fijan al contexto registrado), y `DOCKER_HOST` definido: se acepta solo si se demuestra que es el destino capturado y, si no, el flujo completo (`_with_instance`) aborta sin crear ni aprovisionar nada y limpia el directorio privado. También cubren: `_safe_rmtree` (directorio ya inexistente = limpio; nombre, tipo, enlace simbólico, propietario o `lstat` fallido = `LifecycleError`, sin borrar nada), la política de **Docker solo local** (`unix:///ruta` y loopback verificado aceptados; `ssh://`, `tcp://` remoto, hostnames no verificables, `npipe://`, `fd://` y credenciales rechazados) y el **ID del Docker Engine** (registro al crear, verificación antes de cada búsqueda, estado desconocido si falta, es ilegible o cambia). Verifican que, ante cualquier estado incierto, no se borran las credenciales, el teardown no se declara exitoso y se informa cómo recuperar el contenedor. `pg_test_db.py` las ejecuta (marcador `pg_concurrency_unit`) antes de crear ningún contenedor.
- `../../backend/tests/pg_concurrency/test_harness_unit.py`: pruebas unitarias del arnés (sin base de datos): `join()` explícito frente a `done`, `[CF-LEAK]` y cuarentena de hilos vivos en `verify_clean()`/`seed()`, y `PgContext.finalize()` con la comprobación del pool antes de `dispose()`.
- `../../backend/tests/pg_concurrency/mutation_runner.py` + `mutations.py`: mutaciones sobre **copias** de `backend/` en un directorio temporal fuera de la **raíz completa** del repositorio (no solo de `backend/`); si no cumple esa condición se aborta y se elimina. Además comprueba que `app` se importe desde la copia.

## Alcance de las mutaciones

| Mutación | Debe fallar | Código exigido | Controles que deben pasar |
|---|---|---|---|
| M1-V (sin SKIP LOCKED en Vehicle) | **T3-E** (principal) y T3-D (respaldo) | `LOSER_GOT_VEHICLE` (T3-E: el perdedor obtiene el vehículo ya reservado) y `LOSER_WRONG_ERROR` (T3-D) | T3-C, T3-D-b, controles positivos y de entorno |
| M1-D (sin SKIP LOCKED en Driver) | T3-D-b | `LOSER_GOT_DRIVER` | T3-C, T3-D, T3-E, controles |
| M2 (bloqueo normal) | T3-D, T3-D-b y T3-E | `LOSER_BLOCKED` | T3-C, controles |
| M3 (sin FOR UPDATE del Shipment) | T3-C | `SHIPMENT_LOCK_MISSING` | T3-D, T3-D-b, T3-E, controles |

**T3-E** (2 Shipments, 1 Vehicle, 2 Drivers): A queda detenida antes del commit con el vehículo y un
conductor; B debe terminar sin esperar y recibir 400 por falta de vehículos, sin reservar el segundo
conductor. Con un solo conductor (T3-D) M1-V solo se notaba por el texto del error; con dos, un Vehicle
sin bloqueo se traduce en una doble asignación observable en el estado persistido. Cuando B devuelve 200,
el test comprueba que B obtuvo V1, libera A y espera su resultado, lee el estado persistido final y
confirma que V1 tiene una doble referencia activa; **solo entonces** emite `[CF-DETECT:LOSER_GOT_VEHICLE]`.
Si esa doble referencia no aparece, el fallo es `[CF-INFRA:…]` (no cuenta como detección).

**T3-C y M3:** que el hilo de B termine sin quedar bloqueado por A **no** basta para emitir
`SHIPMENT_LOCK_MISSING`. Solo lo es una segunda asignación efectiva: HTTP 200, `assignment_created`
true y vehículo y conductor distintos de los que A tiene seleccionados. Cualquier otro resultado de
una B que terminó sin bloquearse es `[CF-INFRA:…]`. El criterio vive en una función pura
(`unblocked_second_request_verdict`) con pruebas unitarias en `test_t3c_verdict_unit.py`.

Bajo mutación solo corren las pruebas deterministas (`gated`) y los controles; las de carrera
(`race_stress`) forman parte de la línea base. Si la línea base no pasa completa, no se ejecuta ninguna mutación.
