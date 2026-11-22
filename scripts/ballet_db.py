"""La base d'état de Ballet sur la machine (OPP-79) : `~/.ballet/ballet.db` (`BALLET_HOME` pour un autre dossier).

Toutes les sessions de la machine y lisent et y écrivent : Maestro, le Monitor, les lancements, les Conductors. La
config, elle, reste dans les fichiers TOML (`maestro.toml`, le profil de chaque projet) : la base ne garde que l'état.

Chaque ouverture met la base à la version du plugin. Les migrations sont les fichiers `migrations/NNNN_<nom>.sql`, à côté
de ce script, appliquées dans l'ordre de leur numéro. `PRAGMA user_version`, un entier que SQLite réserve dans l'en-tête
du fichier pour l'application, garde le numéro de la dernière appliquée : 0 pour une base neuve. Une migration dont le
numéro le dépasse est appliquée, dans la même transaction que le nouveau numéro ; les autres jamais. Rouvrir ne refait
donc rien, et deux scripts qui ouvrent en même temps ne migrent pas deux fois (le second attend, relit, ne trouve rien).
Une migration livrée ne change plus : un changement de schéma est une nouvelle migration.

Les migrations ne font que le schéma. La reprise de l'état d'avant la base (`maestro.toml`, `conductors.json`, les
`.ballet/run/` des projets…) n'en est pas une : c'est une commande à part, `ballet_legacy.py import`.

Avant de migrer une base qui a déjà une version, une copie est faite à côté (`ballet.db.v<N>.bak`) : on ne revient en
arrière qu'en la remettant. Une base plus récente que le plugin (un plugin plus neuf l'a migrée) est refusée.

La base est en WAL (lecteurs et écrivain ne se bloquent pas) ; un écrivain attend jusqu'à `BUSY_TIMEOUT_MS` qu'un autre
ait fini. Une écriture qui lit puis modifie passe par `writing` : `BEGIN IMMEDIATE`, un seul écrivain à la fois.
"""

import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

import ballet_state

DB_NAME = "ballet.db"
MIGRATIONS = Path(__file__).resolve().with_name("migrations")
MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
BUSY_TIMEOUT_MS = 10_000


class DatabaseError(Exception):
    """La base ne peut pas servir : le message dit pourquoi."""


ERRORS = (DatabaseError, sqlite3.Error)   # ce qu'une commande attrape pour le dire, au lieu d'une trace


@contextmanager
def reading(state=None):
    """Une connexion pour lire, fermée à la sortie."""
    connection = connect(state)
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def writing(state=None):
    """Une transaction d'écriture : tout passe ou rien ne passe, un seul écrivain à la fois."""
    connection = connect(state)
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")
    finally:
        connection.close()


def connect(state=None, migrations=MIGRATIONS):
    """La base ouverte, à la dernière version du plugin."""
    path = database_path(state)
    connection = _open(path)
    try:
        _migrate(connection, path, _migrations_in(migrations))
    except BaseException:
        connection.close()
        raise
    return connection


def database_path(state=None):
    return ballet_state.state_dir(state) / DB_NAME


def version(connection):
    return connection.execute("PRAGMA user_version").fetchone()[0]


# --- l'ouverture ---------------------------------------------------------------


def _open(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, autocommit=True, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# --- les migrations -------------------------------------------------------------


def _migrate(connection, path, migrations):
    """Applique ce qui manque, sous le verrou d'écriture ; la version se relit une fois le verrou pris."""
    latest = migrations[-1][0] if migrations else 0
    seen = version(connection)
    if seen == latest:
        return
    _refuse_if_newer(seen, latest)
    if seen > 0:
        _back_up(connection, path, seen)
    connection.execute("BEGIN IMMEDIATE")
    try:
        current = version(connection)
        _refuse_if_newer(current, latest)
        missing = [(number, script) for number, script in migrations if number > current]
        for number, script in missing:
            connection.executescript(script.read_text(encoding="utf-8"))
            connection.execute(f"PRAGMA user_version = {number}")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def _migrations_in(folder):
    """Les migrations, (numéro, fichier), dans l'ordre ; un nom hors de la forme `NNNN_<nom>.sql`, ou un numéro en double, est refusé."""
    found = []
    for script in sorted(folder.glob("*.sql")):
        name = MIGRATION_NAME.match(script.name)
        if not name:
            raise DatabaseError(f"migration {script.name} is not named NNNN_<name>.sql")
        found.append((int(name.group(1)), script))
    numbers = [number for number, _ in found]
    if len(set(numbers)) != len(numbers):
        raise DatabaseError(f"two migrations share a number in {folder}")
    return found


def _refuse_if_newer(current, latest):
    if current > latest:
        raise DatabaseError(f"the database is at version {current}, this plugin knows {latest}: "
                            "a newer Ballet migrated it; reinstall the plugin from its clone (/ballet:reset-ballet)")


def _back_up(connection, path, current):
    """Une copie cohérente de la base telle qu'elle est, avant d'y toucher : `ballet.db.v<N>.bak`. Elle se fait avant le
    verrou d'écriture (une copie lit la base : sous son propre verrou elle attendrait sans fin), dans un fichier à part
    renommé ensuite : deux scripts qui migrent ensemble ne s'écrivent pas l'un sur l'autre."""
    target = path.with_name(f"{path.name}.v{current}.bak")
    handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=path.parent)
    os.close(handle)
    copy = sqlite3.connect(temporary)
    try:
        connection.backup(copy)
    finally:
        copy.close()
    os.replace(temporary, target)
