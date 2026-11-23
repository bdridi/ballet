# Ballet — opportunités

Ce qui reste à faire, à vérifier ou à trancher dans Ballet. La méthode est dans `PRD.md`, ce qui est livré dans `release.md`.

- 🆕 à traiter. Un sujet traité sort d'ici : sa version et son numéro sont dans `release.md`.
- Un sujet garde son numéro pour toujours, même sorti d'ici. Pas de doublon : un nouveau besoin proche d'un sujet existant l'enrichit.
- Une ligne par sujet, du plus pressé au plus lointain. Les sujets écartés au ménage du 22/11 (politique et GitHub, réglages des rôles, CLI, profil, petits sujets) restent dans l'historique git ; un vrai run qui les réclame (les frictions le montrent) les rouvre sous un nouveau numéro.

## La vision

- **La file, c'est GitHub.** Une issue a un type (`task`, `bug`, `feature`, `slice`) et un statut ; une `task`, un `bug` ou une `feature` au statut prêt attend sa Rehearsal. Les slices naissent de la planification d'une feature et se jouent à sa suite.
- **Un observateur déterministe** (un script, pas un agent : le Monitor) surveille la file et signale l'élément prêt ; il ne lance rien. C'est Maestro qui lance une session de Conductor neuve, seul pour ce que le projet confie à l'auto, sinon sur le oui du Director. L'état vit dans les scripts et sur GitHub : rien à garder en mémoire d'une session à l'autre.
- **Chaque boucle tourne en `assisted` par défaut**, ou en `autopilot` quand on la lance ainsi.
- **Le Workshop sort une feature prête, jamais un plan.** Le Choreographer y donne son avis technique tôt, parce qu'il peut changer le choix produit. En assisted, le Director, le Dramaturg et le Choreographer ; en autopilot, le Dramaturg et le Choreographer seuls, et la feature sort proposée, prête une fois que le Director l'accepte ; le full autopilot (prête d'emblée) reste une option.
- **La Rehearsal planifie sur le vrai `main`** : le Choreographer commence par le plan, juste avant le Dancer, pour qu'il ne se périme pas. En assisted, elle escalade vers le Director ; en autopilot, c'est le mode nuit.
- **En autopilot, chacun décide dans son périmètre** : le Dramaturg tranche le métier ; le Choreographer l'architecture, et demande le métier au Dramaturg ; le Dancer suit l'architecture, et demande au Choreographer. Ce qui est décidé sans le Director est marqué et réuni dans un rapport du matin ; il ne reçoit en direct que ce qui sort de tous les périmètres.
- **Un budget** borne ce que l'autopilot dépense.
- **Maestro**, le point d'entrée du Director pour plusieurs projets, et le seul à lancer les Conductors (livré, 0.33.0 à 0.39.0).

## À faire

- 🆕 **OPP-77 · Une feature coûte ~4 à 5 $** : sessions courtes, socle des workers et de Maestro allégé, scripts qui résument, lectures ciblées, modèles moins chers, une seule preuve complète (ex-OPP-66, 67, 78).
- 🆕 **OPP-81 · Le terminal de Maestro réutilisé** : `ballet_maestro.py maestro` (et `/ballet:setup`) dit « already there » tant que le terminal noté vit, même quand la session Maestro y est sortie et que l'onglet sert à autre chose ; vérifier que c'est bien Maestro qui y tourne (son agent, son bail) avant de ne rien créer.
- 🆕 **OPP-80 · Reprendre un élément** : un Conductor arrêté repart en plein vol (`ballet_launch.py resume`), et aussi après une escalade avant la PR, un réveil de mutation perdu, une feature déjà planifiée ou une parente avec ses slices (ex-OPP-12, 13, 20, 21).
- 🆕 **OPP-74 · Headless** : Maestro sur un VPS, `orca serve --supervise` sous systemd et un gardien qui garde vivants la boîte, le Monitor et Maestro (refaire le spike 0001 sous Linux).
- 🆕 **OPP-52 · Le rapport du matin** : ce que la nuit a mergé, escaladé et décidé seul ; en Rehearsal autopilot, chaque rôle marque ce qu'il a tranché seul (`ballet:decided-alone`, ex-OPP-07).
- 🆕 **OPP-53 · Le budget de l'autopilot** : un plafond par nuit et par projet ; atteint, Maestro ne lance plus rien et le dit.
- 🆕 **OPP-50 · Un projet hors Rust** : migrer Flownest, avec la mutation TS et JVM (StrykerJS, PIT, recettes dans `init-project`) et plusieurs repos par projet (ex-OPP-16, 17, 47).
