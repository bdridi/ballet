"""Les options communes des sessions Claude que Ballet lance dans un terminal Orca (le Conductor, Maestro) : un socle allégé,
un cache d'une heure, la statusline qui note la capacité.

Une session `claude` démarre avec un socle fixe de tokens (prompt système, définitions d'outils, serveurs MCP du poste,
skills), relu à chaque tour. Mesuré sur `claude -p` (2.1.330), un poste avec quelques plugins et des connecteurs :

    socle par défaut                                   38 100 tokens
    sans serveur MCP (`--strict-mcp-config`)           33 800
    sans serveur MCP, outils du rôle seuls (`--tools`) 17 600

Le skill Ballet reste chargé (le plugin n'est pas touché) : seuls partent les serveurs MCP du poste et les outils intégrés
dont le rôle ne se sert pas (agents, tâches planifiées, worktrees, navigateur…). Le Conductor écrit des fichiers
(`Write`, `Edit`) et lance des scripts (`Bash`) ; Maestro lance des scripts et lit (`Bash`, `Read`), dont l'attente de sa boîte
en arrière-plan. Les deux chargent leurs skills (`Skill`).

Maestro porte aussi `PushNotification` (OPP-91), l'outil qui prévient l'appareil du Director quand une escalade ou une demande
l'attend : `--tools` l'accepte tel quel (il est chargé, pas différé derrière `ToolSearch`). Mesuré (2.1.331, mêmes conditions) :
+ 577 tokens de socle, relus à chaque tour de Maestro (16 870 → 17 447). `[maestro] push = false` le retire, à la création de la
session. L'outil n'envoie vers le mobile que si Remote Control est connecté (Maestro est lancé avec `--remote-control`) et que
le réglage `agentPushNotifEnabled` de Claude Code est vrai (`/config`, « push when Claude decides ») ; sinon il répond « not sent »
sans rien lever.

Le cache de prompt dure une heure (`CLAUDE_CODE_PROMPT_CACHE_TTL=1h`, Claude Code ≥ 2.1.242) : au-delà du quota d'abonnement,
ou sur une clé d'API, le défaut tombe à 5 minutes, et chaque attente (mutation, Critic) réécrit tout le contexte.

La statusline (`ballet_statusline.py`, OPP-88) est le seul endroit où Claude Code donne la part consommée de ses fenêtres de
5 heures et de 7 jours (`rate_limits`) : `--settings` la branche sur ces sessions, et la commande lance à la suite celle de
l'utilisateur (Orca), qu'un `--settings` remplacerait sinon. Seules les sessions de Maestro et des Conductors la portent : la
fenêtre est celle du compte, n'importe laquelle la voit.

Les workers (`ballet_orca.start_worker`) n'ont ni l'un ni l'autre : `orca orchestration worker-start` n'accepte que
`--model` et `--effort`, pas d'options ni de variables pour `claude`. Orca les lit dans ses propres réglages d'agent
(`agentDefaultArgs` et `agentDefaultEnv`, par agent, pour tout lancement), que le Director pose une fois dans Orca.
"""

import json
import shlex
from pathlib import Path

CACHE_TTL_VARIABLE = "CLAUDE_CODE_PROMPT_CACHE_TTL"
CACHE_TTL = "1h"
NO_MCP_SERVERS = ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
CONDUCTOR_TOOLS = "Bash,Read,Write,Edit,Skill"
MAESTRO_TOOLS = "Bash,Read,Skill"
PUSH_TOOL = "PushNotification"
STATUSLINE_SCRIPT = Path(__file__).with_name("ballet_statusline.py")


def lean_options(tools):
    """Les options d'une session sans serveur MCP, avec les seuls outils intégrés donnés (`--tools`)."""
    return [*NO_MCP_SERVERS, "--tools", tools]


def maestro_tools(push):
    """Les outils de Maestro : ceux de son rôle, plus l'outil de push (`PushNotification`) quand `[maestro] push` le veut."""
    return f"{MAESTRO_TOOLS},{PUSH_TOOL}" if push else MAESTRO_TOOLS


def statusline_options():
    """Les options qui branchent la statusline de Ballet (`--settings`, un JSON : le chemin du script est quoté dedans)."""
    command = f"python3 {shlex.quote(str(STATUSLINE_SCRIPT))}"
    return ["--settings", json.dumps({"statusLine": {"type": "command", "command": command}})]


def with_environment(command, variables):
    """La commande précédée de ses variables d'environnement (`NOM=valeur`), plus celle du cache d'une heure.
    `variables` : nom → valeur, dans l'ordre où elles sont posées."""
    assignments = {**variables, CACHE_TTL_VARIABLE: CACHE_TTL}
    return " ".join([*(f"{name}={shlex.quote(value)}" for name, value in assignments.items()), command])
