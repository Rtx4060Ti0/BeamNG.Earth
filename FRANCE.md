# Correctifs France sur BeamNG.Earth 1.7.1-beta

Ce profil reste expérimental. Il ne constitue pas une validation de toutes les routes de France.

## Lancement

Installer les dépendances de `server/requirements.txt`, puis lancer
`python start_corrected.py --user-dir "<dossier utilisateur BeamNG>"`.
`--game-dir "<dossier du jeu>"` précise une installation non détectée.
Sous Windows, `Lancer-BeamNG-France.cmd` transmet les mêmes arguments.
Le module natif Windows a été reconstruit avec les corrections de raccord.
Sur Linux, reconstruire `python3 tools/build_native.py` : le binaire Linux
fourni par la version officielle ne contient pas encore ces changements.

Le lanceur compare le mod à sa source, sauvegarde la version remplacée et lance
le serveur correspondant. Il refuse de remplacer le mod pendant que le jeu tourne.
`--check` affiche les empreintes sans modifier l'installation.
La configuration utilise aussi `BNE_USER_DIR`, `BNE_GAME_DIR` et éventuellement
`BNE_FRANCE_DB` (index créé par `tools/build_france_index.py`).

Le gestionnaire Windows `managed_launcher/start.py` conserve des versions sous
`versions/`, contrôle leur manifeste SHA-256 et choisit celle de `current.json`.
Sa configuration locale est dans `local-config.json`, hors Git. Les raccourcis
qui l'utilisent conservent le profil à chaque redémarrage. Un lancement direct par
Steam ou par un nouvel EXE officiel ne passe pas par lui. Les futures versions
officielles doivent être adaptées et testées avant de remplacer la version validée.

## Changements

- Relief IGN RGE ALTI activable en France, avec repli mondial si indisponible.
- Toitures rectangulaires évitées lorsqu'elles débordent du contour du bâtiment.
- Profils et ouvertures de tunnels, passages route/rail et ponts piétons.
- Attente des collisions avant de poser la voiture après téléportation.
- Relance des processus de génération bloqués, avec délai maximal par tâche.
- Trottoirs flottants ou traversant une chaussée de pont retirés.
- Raccords entre tabliers voisins du même niveau, suppression des surfaces
  superposées et texture d'asphalte commune.
- Les ponts courts sur une très longue route ne sont plus éliminés par un seuil
  exprimé en fraction de la longueur totale.
- Lissage de tablier sans rabattement vertical final ; atténuation progressive
  de l'influence d'une route voisine à un autre niveau sur la chaussée.
- Un passage sous ouvrage estimé ne creuse plus un terrain au-dessus de la mer
  jusqu'à une hauteur qui l'inonde. Le dégagement sous le pont reste à vérifier
  lorsque cette excavation est refusée.
- Sens interdits déduits des sens uniques cartographiés aux carrefours. Le poteau
  est placé automatiquement : sa position n'est pas un relevé de terrain.
- Chemins piétons et cyclables rendus sans les ajouter au réseau automobile.
  Les escaliers restent des surfaces inclinées, pas des marches fidèles.
- Noms de 38 515 villes et villages visibles par défaut sur la carte. Le choix
  d'affichage est mémorisé ; les lieux-dits de l'index local restent des repères.

## Données et limites

Les noms de `franceplaces.js` viennent d'OpenStreetMap, extrait France du 12 octobre
2026, sous ODbL. Voir [CREDITS.md](CREDITS.md). Le SQLite et le PBF ne sont pas
distribués avec le code. Les caches évitent certains recalculs, mais ne gardent pas
toute la France en RAM.

Les essais de conduite sont distincts des contrôles calculés :
[validation](docs/FRANCE_VALIDATION.md). Des défauts restent signalés sur
l'ouvrage ferroviaire près de Serrières, les raccords complexes d'Annonay et les
trottoirs de certaines rues. Les façades et monuments absents des données restent
estimés. Un audit national des données ne garantit pas chaque collision en jeu.

## Contrôle de l'extrait France

`python tools/audit_france_index.py <index.sqlite> <nouveau-dossier-rapport>`
lit tous les tronçons de l'index terminé, sans le modifier. Le rapport et la liste
des points à examiner sont publiés après vérification des compteurs et de
l'intégrité SQLite. L'extrait du 12 octobre 2026 couvre la métropole et la Corse,
pas l'outre-mer. Le contrôle du 29 octobre a lu 12 404 901 tronçons ; 6 310 sont
à examiner, dont 3 308 motorisés. Une alerte n'est pas une route certifiée cassée.
