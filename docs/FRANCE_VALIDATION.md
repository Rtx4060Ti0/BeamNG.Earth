# Validation du profil France

Base actuelle : BeamNG.Earth 1.7.1-beta, commit 8aaf4ebdd0485facadc755a612f4b0a2b55e4c57.
Profil candidat : 1.7.1-beta-france.1, 30 octobre 2026.

## Validation de la mise à jour 1.7.1

Module natif Windows reconstruit à partir des sources du profil. Linux doit
reconstruire le module ; aucun essai Linux n'a été effectué.

- Géométrie : 188 tests réussis (profils, approches, raccords, ponts courts,
  séparation des routes, régression de dévers I-80).
- Intégration ciblée : 253 tests, 252 réussis et 1 ignoré ; signalisation et
  tabliers joints : 7 tests réussis.
- Lua : placement 1207, client simulé 280, robustesse 66, maintien de chute 35,
  pause 5, routes 92 et réglages 268 assertions réussies.
- Le test réseau `SessionCreditsTest.test_session` expire en attendant
  `far_done` après un déplacement de 50 km. Même expiration reproduite sur la
  version officielle 1.7.1 sans correctifs. Ce test n'est pas compté comme réussi.
- Sur les profils calculés A7 au sud de Saint-Vallier, la marche liée au seuil
  de mélange des chaussées diminue fortement. Un autre raccord présente encore
  une pente maximale de 28,5 % ; il reste à corriger.
- Le tablier du chemin de la Bouterne ne présente plus le rabattement vertical
  du lissage, mais reste trop raide (40,8 %). Ses hauteurs d'approche restent
  incohérentes. Rue Gaston-Duclos à Annonay : raccord encore anormal (42,6 %).

Ces mesures portent sur des axes échantillonnés, pas sur toute la largeur,
les collisions ou toutes les routes de France. Le contrôle utilise maintenant
le décodeur cartographique du serveur, avec ses corrections de niveaux.
Les sites aux données absentes sont comptés comme incomplets.

## Contrôles calculés antérieurs (base 1.7.0)

- Suite ciblée : 188 tests Python réussis (routes, tabliers, signalisation,
  index France, crédits, processus, séparations de niveaux).
- Après le correctif de creusement : 52 tests ciblés réussis, dont le nouveau
  cas de terrain sec abaissé sous le niveau marin.
- Lua : placement 1207, client simulé 280, robustesse 66, maintien de chute 35,
  gestion de pause 5 assertions réussies.
- Rue Hélène-Boucher à Montpellier : avec les mêmes données IGN et routières,
  profil initial -3,973 à +6,302 m, profil corrigé +3,517 à +6,302 m.
  Mesure de génération, pas un essai physique. Hauteurs brutes : +3,423 à +6,280 m.

## Essais en jeu précédents

Profil france.2 : 92 m parcourus rue du Québec sans dégâts détectés et 92 m sur
la partie centrale du viaduc Daniel-Aimé sans dégâts détectés. Cela ne valide pas
les carrefours aux extrémités. Profil france.3 : mesure transversale du raccord
central réduite d'environ 25,7 cm à 0,6 cm ; l'aspect restait imparfait.

Les essais de la version candidate seront consignés après installation.
Les résultats précédents ne doivent pas être attribués à une nouvelle version.

## Régressions à contrôler

| Secteur | Coordonnées approximatives | Défaut signalé |
| --- | --- | --- |
| Montpellier, rue Hélène-Boucher | 43.58140, 3.94327 | chaussée inondée après creusement |
| Serrières, ligne de Givors-Canal à Grezan | 45.31744, 4.76511 | ouvrage anormalement haut |
| Annonay, rue Étienne-Frachon | 45.24674, 4.66237 | trottoirs et bâtiment dans la route |
| Annonay, rue du Québec | 45.24780, 4.67843 | raccords et trottoirs superposés |
| Annonay, viaduc Daniel-Aimé | 45.24792, 4.67663 | raccord et extrémités |
| Tournon, passerelle piétonne | 45.0690, 4.8355 | ouvrage absent |

Un audit national des données ne remplace pas des essais de collisions et de
conduite. Une alerte est un point à examiner, pas la preuve d'une erreur réelle.

## Audit de l'index national, 29 octobre 2026

Extrait France métropolitaine et Corse, horodatage OSM 2026-10-12T20:21:35Z.
12 404 901 tronçons lus jusqu'à la fin, dont 7 331 557 motorisés, 256 173 tronçons
de ponts et 62 450 de tunnels. Compteurs conformes au manifeste, SQLite
`quick_check=ok`, source inchangée. 6 310 tronçons à examiner, dont 3 308 motorisés.
Les seuils de pente, largeur et hauteur sont des critères de tri, pas des normes
de conception ni la preuve que le générateur se trompe. L'index ne contient pas
les altitudes, les collisions ni les contours de bâtiments.

SHA-256 de l'index : à lire dans le rapport local `rapport.json`.
Quatre tests des règles de lecture des unités, pentes, niveaux et références passent.
L'essai en jeu du candidat a été interrompu par une mise à jour utilisateur de
BeamNG.Earth vers 1.7.1 et de BeamNG.drive via Steam : aucune nouvelle validation
physique complète n'est revendiquée.
