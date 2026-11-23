"""Les options communes des sessions Claude que Ballet lance dans un terminal Orca (le Conductor, Maestro) : un socle allégé,
un cache d'une heure.

Une session `claude` démarre avec un socle fixe de tokens (prompt système, définitions d'outils, serveurs MCP du poste,
skills), relu à chaque tour. Mesuré sur `claude -p` (2.1.330), un poste avec quelques plugins et des connecteurs :

    socle par défaut                                   38 100 tokens
    sans serveur MCP (`--strict-mcp-config`)           33 800
    sans serveur MCP, outils du rôle seuls (`--tools`) 17 600

Le skill Ballet reste chargé (le plugin n'est pas touché) : seuls partent les serveurs MCP du poste et les outils intégrés
dont le rôle ne se sert pas (agents, tâches planifiées, worktrees, navigateur…). Le Conductor écrit des fichiers
(`Write`, `Edit`) et lance des scripts (`Bash`) ; Maestro lance des scripts et lit (`Bash`, `Read`), dont l'attente de sa boîte
en arrière-plan. Les deux chargent leurs skills (`Skill`).

Le cache de prompt dure une heure (`CLAUDE_CODE_PROMPT_CACHE_TTL=1h`, Claude Code ≥ 2.1.242) : au-delà du quota d'abonnement,
ou sur une clé d'API, le défaut tombe à 5 minutes, et chaque attente (mutation, Critic) réécrit tout le contexte.

Les workers (`ballet_orca.start_worker`) n'ont ni l'un ni l'autre : `orca orchestration worker-start` n'accepte que
`--model` et `--effort`, pas d'options ni de variables pour `claude`. Orca les lit dans ses propres réglages d'agent
(`agentDefaultArgs` et `agentDefaultEnv`, par agent, pour tout lancement), que le Director pose une fois dans Orca.
"""

import shlex

CACHE_TTL_VARIABLE = "CLAUDE_CODE_PROMPT_CACHE_TTL"
CACHE_TTL = "1h"
NO_MCP_SERVERS = ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
CONDUCTOR_TOOLS = "Bash,Read,Write,Edit,Skill"
MAESTRO_TOOLS = "Bash,Read,Skill"


def lean_options(tools):
    """Les options d'une session sans serveur MCP, avec les seuls outils intégrés donnés (`--tools`)."""
    return [*NO_MCP_SERVERS, "--tools", tools]


def with_environment(command, variables):
    """La commande précédée de ses variables d'environnement (`NOM=valeur`), plus celle du cache d'une heure.
    `variables` : nom → valeur, dans l'ordre où elles sont posées."""
    assignments = {**variables, CACHE_TTL_VARIABLE: CACHE_TTL}
    return " ".join([*(f"{name}={shlex.quote(value)}" for name, value in assignments.items()), command])
