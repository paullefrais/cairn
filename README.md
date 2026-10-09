# Cairn

Prototype d'outil d'aide à la décision pour les organisateurs de trail en montagne, appliqué aux données réelles du **Challenge du Montcalm** et du **Grand Raid des Pyrénées**.

**Démo en ligne : https://paullefrais.github.io/cairn/**

![Aperçu de Cairn](apercu.png)

## Le problème

Un organisateur de trail prend chaque année les mêmes décisions, souvent à l'expérience : combien de nourriture et de bénévoles à chaque ravitaillement, combien de navettes et à quelle heure, où placer les barrières horaires, quel plan de repli si la météo tourne. Cairn utilise les temps de passage des éditions précédentes pour rendre ces décisions plus sûres.

## Ce que montre le prototype

Une page d'accueil présente les événements couverts, leurs courses et la date de la prochaine édition. Chaque course (7 au Challenge du Montcalm, 7 au Grand Raid des Pyrénées) a le même écran :

- **Vue d'ensemble** : partants attendus, taux d'abandon, point le plus chargé, profil du parcours, points à décider et historique des éditions.
- **Ravitaillements** : coureurs attendus par quart d'heure à chaque point avec leur fourchette (survol pour le détail d'un créneau), quantités et bénévoles. Un mode « Test » compare la prévision faite avec les années précédentes au réel de la dernière édition.
- **Navettes et rapatriements** : besoins heure par heure et lieux d'abandon, prévus et observés.
- **Course en direct** : rejeu de la dernière édition avec les vrais temps de passage, repères tête de course, peloton et derniers coureurs, et état des barrières horaires.
- **Pertes alimentaires** et **Scénarios météo** : onglets en attente, avec des données fictives.

L'heure de départ est modifiable (toutes les heures affichées se décalent) et un bouton bascule entre thème clair et sombre.

## Les données

Temps de passage publiés sur LiveTrail (Montcalm 2022-2026, GRP 2021-2026), **anonymisés** : aucun nom n'est conservé, un identifiant haché avec un sel jamais enregistré permet seulement de reconnaître un même coureur d'une année à l'autre. Les ratios de consommation, de bénévoles et de navettes sont des hypothèses à valider avec l'organisation.

## Structure

- `index.html` : l'interface, sans serveur ni dépendance.
- `data/montcalm.js`, `data/grp.js` : prévisions et historique de chaque course, générés par `outils/build_event.py`.
- `logos/` : emplacement des logos (voir `logos/LISEZMOI.md`).
- `outils/cairn_model.py` : le modèle de prédiction (version générique du notebook `cairn_prediction.ipynb`).
- `outils/recuperer_livetrail.js` : le script de récupération anonymisée, à coller dans la console du navigateur sur un onglet LiveTrail (changer le préfixe `montcalm_` pour un autre événement, par exemple `grp_`).
- `outils/alias_grp.json` : correspondances entre les noms de points qui changent d'une année à l'autre.

Pour régénérer les données : placer `cairn_montcalm_livetrail.json` ou `cairn_grp_livetrail.json` dans `data/`, puis lancer `python3 outils/build_event.py montcalm` (ou `grp`) depuis la racine (numpy et pandas requis). Les fichiers bruts ne sont pas publiés dans le dépôt.

L'adresse du bouton contact se règle dans `index.html` (constante `CONTACT_EMAIL`).

## Contact

Projet porté par Paul Lefrais, élève ingénieur à ISAE-Supaero.
Vous organisez une course et voulez donner votre avis ? Écrivez-moi sur [LinkedIn](https://www.linkedin.com/in/paullefrais).
