"""Le dossier d'état de Ballet sur la machine (`~/.ballet`, ou `BALLET_HOME`) : où il est, comment on y écrit, comment on s'y verrouille.

`ballet_maestro.py` (sa config), `ballet_conductors.py` (le registre des Conductors) et `ballet_launch.py` (les lancements)
y écrivent : ce module est ce qu'ils ont en commun. Il ne sait rien de ce qu'ils y mettent.
"""

import fcntl
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

DEFAULT_LOCK = "maestro.lock"


def state_dir(state=None):
    return Path(state or os.environ.get("BALLET_HOME") or Path.home() / ".ballet")


def write_atomically(path, text):
    """Un fichier temporaire à côté, puis un renommage ; un lecteur voit l'ancien contenu ou le nouveau, jamais la moitié."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


@contextmanager
def locked(state=None, name=DEFAULT_LOCK):
    """Un seul appel à la fois tient ce verrou. Il n'est pas réentrant : qui le tient n'appelle rien qui le reprenne."""
    folder = state_dir(state)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / name, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
