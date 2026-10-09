# Cairn

Prototype d'outil d'aide à la décision pour les organisateurs de trail en montagne, appliqué aux données réelles du **Challenge du Montcalm**.

**Démo en ligne : https://paullefrais.github.io/cairn/**

![Aperçu de Cairn](apercu.png)

## Le problème

Un organisateur de trail prend chaque année les mêmes décisions, souvent à l'expérience : combien de nourriture et de bénévoles à chaque ravitaillement, combien de navettes et à quelle heure, où placer les barrières horaires, quel plan de repli si la météo tourne. Cairn utilise les temps de passage des éditions précédentes pour rendre ces décisions plus sûres.

## Ce que montre le prototype

Un même écran pour chacune des sept courses du Challenge (Marathon, PicAriège, PICaPICA, Novis, Mineurs, KV, By Night), à choisir en haut de page :

- **Vue d'ensemble** : partants attendus, taux d'abandon, point le plus chargé, profil du parcours, points à décider et historique des éditions.
- **Ravitaillements** : coureurs attendus par quart d'heure à chaque point avec leur fourchette, quantités et bénévoles. Un mode « Test » compare la prévision faite avec les années précédentes au réel de la dernière édition.
- **Navettes et rapatriements** : besoins heure par heure et lieux d'abandon, prévus et observés.
- **Course en direct** : rejeu de la dernière édition avec les vrais temps de passage et l'état des barrières horaires.
- **Pertes alimentaires** et **Scénarios météo** : onglets en attente, avec des données fictives.

L'heure de départ est modifiable : toutes les heures affichées se décalent.

## Les données

Temps de passage publiés sur LiveTrail pour les éditions 2022 à 2026, **anonymisés** : aucun nom n'est conservé, un identifiant haché avec un sel jamais enregistré permet seulement de reconnaître un même coureur d'une année à l'autre. Les ratios de consommation, de bénévoles et de navettes sont des hypothèses à valider avec l'organisation.

## Structure

- `index.html` : l'interface, sans serveur ni dépendance.
- `data/montcalm.js` : les prévisions et l'historique de chaque course, générés par `outils/build_montcalm.py`.
- `outils/cairn_model.py` : le modèle de prédiction (version générique du notebook `cairn_prediction.ipynb`).
- `outils/recuperer_livetrail.js` : le script de récupération anonymisée, à coller dans la console du navigateur sur un onglet LiveTrail.

Pour régénérer les données : placer `cairn_montcalm_livetrail.json` dans `data/`, puis lancer `python3 outils/build_montcalm.py` depuis la racine (numpy et pandas requis). Le fichier brut n'est pas publié dans le dépôt.

## Contact

Projet porté par Paul Lefrais, élève ingénieur à ISAE-Supaero.
Vous organisez une course et voulez donner votre avis ? Écrivez-moi sur [LinkedIn](https://www.linkedin.com/in/paullefrais).
