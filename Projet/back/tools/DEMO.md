# Déroulé de démonstration | Under

À imprimer ou garder ouvert sur un second écran.

---

## Configuration de démonstration

**Ne rien mettre dans `back/.env` à part la ligne ci-dessous.** Les valeurs par
défaut de `config/settings.py` sont celles sur lesquelles les seuils ont été
calibrés, et ce sont donc les seules qui rendent les chiffres du mémoire
défendables. Toute surcharge dans le `.env` désaligne la démonstration de la
mesure publiée.

```env
DEBUG=False
```

Pour mémoire, la configuration effective est alors une fenêtre de 3 secondes, un
échantillonnage du visage toutes les 0,35 seconde, un seuil de déclenchement à
0,80, des paliers à 1,5 et 1,8, une alerte dès la première fenêtre dissonante et
un délai réfractaire de 5 secondes.

Un contrôle rapide avant de commencer :

```bash
python -m tools.preflight --rapide
```

La section « Cohérence de la configuration » doit annoncer la fenêtre alignée sur
la calibration. Si elle affiche un avertissement, c'est qu'une surcharge traîne
dans le `.env`.

---

## La veille

1. `python -m tools.preflight` — tout doit être vert.
2. **Enregistrer une vidéo de secours** d'une session qui marche : écran + son,
   trois minutes. C'est votre filet si le direct échoue. Ne passez pas sans.
3. Choisir les extraits à jouer et vérifier qu'ils déclenchent bien une alerte.
4. Charger la montre.

---

## Trente minutes avant

```powershell
cd Projet\back
.\venv\Scripts\activate
python -m tools.preflight --sans-ble
```

Le chargement des modèles prend jusqu'à une minute au premier lancement : ne le
faites pas devant le jury.

---

## Ordre de lancement

| # | Action | Attendre |
|---|---|---|
| 1 | `python -m api.main` | la ligne `Application startup complete` |
| 2 | `npm run dev` dans `front/` | la fenêtre HUD |
| 3 | Ouvrir la visio ou la vidéo de test | l'image du visage |
| 4 | Positionner le cadre du HUD sur le visage | le cadre doit le contenir entièrement |
| 5 | Connecter la montre (icône du widget) | LED **BLE** verte |
| 6 | Cliquer « Démarrer l'assistance » | LED **Capteur** verte |

**Les trois LED vertes = le système mesure.** Si la LED Capteur reste rouge, le
cadre n'est pas sur le visage ou il est trop petit.

---

## Pendant

La jauge du widget bouge à chaque fenêtre, même sans alerte. C'est ce qu'il faut
montrer en premier : **le système mesure en continu**, il n'attend pas un
événement pour prouver qu'il est vivant.

Ce qu'il faut dire pendant que ça tourne :

- la barre affiche l'écart mesuré entre le point du visage et celui de la voix
  dans le plan de Russell ;
- elle reste basse quand les deux canaux concordent ;
- quand elle passe le seuil, l'alerte se gradue, et la montre ne vibre qu'à
  partir du niveau modéré, le niveau vigilance restant à l'écran, ce qui évite
  d'interrompre le praticien sur un écart léger ;
- une fois la montre partie, un délai réfractaire de 5 secondes empêche une
  dissonance qui dure de faire vibrer à chaque fenêtre ;
- rien ne sort du poste : ni image, ni son, ni donnée vers un serveur.

Puis basculer sur le tableau de bord : frise chronologique, plan de Russell au
clic sur un pic, notes cliniques, export PDF.

**Referme le panneau de paramètres avant de lancer l'analyse.** Son fond sombre
recouvre la zone capturée et efface l'expression du visage. C'est mesuré : huit
fenêtres sur huit déclenchent une alerte panneau fermé, zéro panneau ouvert, et
le modèle répond « visage neutre » avec 90 % de confiance sans signaler la
moindre difficulté. Le widget normal, lui, ne gêne pas.

---

## Si ça tourne mal

| Symptôme | Cause probable | Réaction |
|---|---|---|
| LED Capteur rouge | cadre mal placé ou visage trop petit | agrandir le cadre, le recentrer |
| Jauge figée à 0 | pas de son capté | paramètres → tester le son → changer de périphérique |
| Aucune alerte ne se déclenche | l'extrait n'est pas assez dissonant | passer à l'extrait de secours, ou tester la vibration depuis les paramètres |
| La montre ne vibre pas | BLE déconnecté | paramètres → tester le bracelet ; sinon commenter, ce n'est pas bloquant |
| Le backend plante | quelconque | **passer à la vidéo de secours sans hésiter**, et enchaîner |

Ne débuggez jamais devant le jury. Vous avez une vidéo : servez-vous-en et
continuez à parler.

---

## Le cadrage à tenir

Ce n'est pas un produit fini, et le référentiel ne vous en demande pas un. Le
document Epitech dit du mémoire exploratoire que la création d'un MVP « n'est
généralement pas applicable », et qu'un « prototype initial pourrait être
envisagé pour tester la théorie ou l'hypothèse développée ».

C'est exactement ce que vous montrez : un prototype qui teste une hypothèse, et
dont la performance a été mesurée sur un jeu de 344 enregistrements étiquetés,
dont 227 exploitables. Présentez la démonstration comme la matérialisation du
protocole, pas comme la démonstration d'un succès commercial.
