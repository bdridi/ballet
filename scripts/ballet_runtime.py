"""L'état de la machine (OPP-79) : la ligne unique de la table `runtime` de la base (`ballet_db.py`).

Ce que les scripts créent ou notent en tournant, jamais la config (qui reste dans `maestro.toml`) :

    mailbox_terminal, mailbox_run   la boîte de Maestro : son terminal Orca et la Run créée `--from` lui
    mailbox_previous_run            la Run d'une boîte recréée, que `recap` relit une dernière fois puis oublie
    maestro_terminal                où tourne la session Maestro (`ballet_maestro.py maestro`)
    monitor_terminal                où tourne le Monitor (`ballet_maestro.py monitor`)
    restart_terminal                le terminal `maestro-restart` d'un redémarrage en cours ; vide sinon
    restart_owns_pause              ce redémarrage a posé la pause : il la retire à la fin
    paused_at                       la pause (`ballet_maestro.py pause`) : plus rien ne part seul ; vide sans pause
    lease_owner, lease_pid,         le bail de lecture de la boîte : le jeton de la session Maestro, le processus de son
    lease_renewed_at, lease_session attente en cours (0 sinon), sa dernière prise, l'id de sa session Claude
    context_told_session            la session Maestro dont le Monitor a signalé le contexte au-delà du seuil
    maestro_version, monitor_version  la version du plugin que la session Maestro (à son `claim`) et le Monitor (à son `run`)
                                    ont chargée en démarrant (`ballet_version.py`, OPP-90) ; vide pour un processus qui n'a rien noté

Une valeur absente se lit `""` (ou 0, ou faux) : on ne teste jamais `None`.
"""

import ballet_db

FIELDS = {
    "mailbox_terminal": "", "mailbox_run": "", "mailbox_previous_run": "", "maestro_terminal": "", "monitor_terminal": "",
    "restart_terminal": "", "restart_owns_pause": False, "paused_at": "", "lease_owner": "", "lease_pid": 0,
    "lease_renewed_at": "", "lease_session": "", "context_told_session": "", "maestro_version": "", "monitor_version": "",
}
LEASE = ("lease_owner", "lease_pid", "lease_renewed_at", "lease_session")


def read(state=None):
    """Tout l'état de la machine : nom → valeur."""
    with ballet_db.reading(state) as connection:
        return read_in(connection)


def read_in(connection):
    """Comme `read`, dans une transaction déjà ouverte : lire puis écrire sans qu'un autre passe entre les deux."""
    row = connection.execute("SELECT * FROM runtime WHERE one = 1").fetchone()
    return {name: _value(row[name], empty) for name, empty in FIELDS.items()}


def update(state=None, **values):
    """Change les valeurs nommées, d'un coup."""
    with ballet_db.writing(state) as connection:
        update_in(connection, **values)


def update_in(connection, **values):
    unknown = sorted(set(values) - set(FIELDS))
    if unknown:
        raise ValueError(f"not a runtime field: {', '.join(unknown)}")
    if values:
        assignments = ", ".join(f"{name} = ?" for name in values)
        connection.execute(f"UPDATE runtime SET {assignments} WHERE one = 1", [_stored(value) for value in values.values()])


def empty_lease():
    return {name: FIELDS[name] for name in LEASE}


def _value(stored, empty):
    if stored is None:
        return empty
    return bool(stored) if isinstance(empty, bool) else stored


def _stored(value):
    if value == "":
        return None
    return int(value) if isinstance(value, bool) else value
