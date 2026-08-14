# Backend | Détection de dissonance émotionnelle

Backend Python (FastAPI) qui analyse en temps réel les expressions faciales et
la voix pour détecter une dissonance émotionnelle, et déclenche une vibration
sur une montre connectée. Tout tourne en local, sur CPU.

## Principe

Le système capture deux canaux **sur le même intervalle de temps** et les
projette dans le plan de Russell (valence / arousal).

**Fenêtre d'analyse.** Une itération = un intervalle de 3 s. L'audio est
enregistré en continu sur cet intervalle, et le visage est échantillonné
*pendant* cet enregistrement (une image toutes les 0,35 s, soit environ 8
images). Les deux canaux décrivent donc le même moment. La version précédente
capturait une seule image *après* les 3 s d'audio : elle comparait un instantané
à une moyenne prosodique, et manquait toute expression apparue en début de
fenêtre.

**Visage.** MediaPipe localise le visage dans la zone du HUD, puis EmotiEffLib
(EfficientNet multi-tâches entraîné sur AffectNet, servi en ONNX) classe chaque
image. Le modèle renvoie 8 probabilités d'émotion **et** une régression
valence/arousal : le point mesuré ne dérive pas du label. La fenêtre est résumée
par la **médiane** des points, plus robuste qu'une moyenne à une image aberrante
(flou de compression, clignement, cadrage raté), accompagnée d'une
**dispersion** : si le visage a trop varié dans la fenêtre, aucun point ne le
représente et la fenêtre est écartée.

**Voix.** Le flux audio est intercepté en loopback (16 kHz) et analysé par le
modèle audeering `wav2vec2-large-robust-12-ft-emotion-msp-dim`, qui renvoie
directement un point (valence, arousal). La fenêtre est découpée en
sous-fenêtres recouvrantes et la **concordance** de leurs estimations sert
d'indice de fiabilité. Le modèle étant une régression, il ne fournit aucune
probabilité ; l'approche précédente assimilait la fiabilité à l'intensité
émotionnelle, ce qui faisait rejeter les voix atones, c'est-à-dire une partie
des masquages recherchés.

**Ruptures de contexte.** La mémoire d'un canal est purgée dès qu'il perd son
signal exploitable (silence, visage absent), et les fenêtres de reprise sont
ignorées. Sans cela, le premier visage d'une nouvelle scène serait comparé à la
voix de la scène précédente.

**Fusion.** La dissonance est la distance euclidienne entre les deux points. Une
logique floue gradue l'alerte en trois niveaux (VIGILANCE / MODERATE / SEVERE).
La fusion exige que **les deux** canaux soient exploitables : une dissonance est
une comparaison, si l'un des deux points n'est pas fiable l'écart entre eux ne
signifie rien.

**Actuation.** La vibration n'est envoyée que sur MODERATE/SEVERE, et hors délai
réfractaire. Elle part dès la **première** fenêtre dissonante : la règle de
persistance existait quand une seule image pouvait porter la décision, mais
chaque fenêtre agrège désormais une dizaine d'images résumées par une médiane,
donc le filtrage des erreurs transitoires a déjà lieu à l'intérieur de la
fenêtre. Exiger une seconde fenêtre faisait doublon, au prix de trois secondes
de retard qui repoussaient l'alerte hors du silence visé. Le délai réfractaire
reste le seul rempart contre la fatigue d'alarme. Le raccrochage de l'appel
simulé part en tâche de fond : il fait partie du motif de vibration, pas de la
latence d'alerte.

**Chemin de capture.** L'image capturée circule en mémoire sous forme de tableau
NumPy, sans encodage intermédiaire. La version précédente encodait en JPEG puis
en base64 pour décoder aussitôt dans le même processus : à raison de huit images
par fenêtre, ce cycle coûtait du temps CPU et ajoutait une troisième compression
au signal, après celle de la visioconférence et celle du rendu écran, sur le
flux même dont on analyse les détails fins.

**Exécution.** Chaque ressource bloquante a son propre exécuteur à un seul
thread : capture audio, inférence faciale, inférence vocale. Les moteurs
embarqués ne sont pas tous thread-safe (l'interpréteur TFLite de MediaPipe ne
l'est pas), et le pool partagé d'`asyncio.to_thread` faisait migrer chaque appel
d'un thread à l'autre.

> Le référentiel de coordonnées universelles par émotion (`EMOTION_COORDINATES`)
> n'intervient plus dans la mesure : les deux modèles produisent nativement leur
> propre point continu. Il ne sert plus qu'à nommer le point le plus proche pour
> l'affichage.

## Structure

```
back/
├── api/
│   └── main.py              # FastAPI, endpoint WebSocket, boucle d'analyse
├── config/
│   └── settings.py          # Constantes du pipeline, coordonnées de Russell
├── services/
│   ├── analysis_session.py  # Décision par fenêtre : ruptures, gradation, cooldown
│   ├── ble_service.py       # Communication BLE avec la montre (protocole Moyoung)
│   └── emotion_service.py   # Détection faciale + vocale, calcul de dissonance
├── utils/
│   └── screen_capture.py    # Capture de la zone du HUD
├── models/
│   └── face_detector.task   # Modèle MediaPipe
├── tools/                   # Bancs de mesure hors ligne (voir tools/README.md)
├── crema_labels.csv         # Jeu étiqueté dérivé de CREMA-D, corpus entier
├── crema_labels_strict.csv  # Idem, restreint aux perceptions nettes
├── crema_congruents.txt     # Listes brutes produites par crema_incongruence.py
├── crema_discordants.txt
├── download_model.py        # Téléchargement du modèle MediaPipe
├── .env.example             # Configuration de référence
└── requirements.txt
```

Les quatre fichiers `crema_*` sont versionnés à dessein. Ce sont eux qui rendent
les mesures reproductibles : les médias, trop lourds, ne le sont pas, mais
n'importe qui peut les retélécharger et retrouver exactement le même jeu
d'évaluation à partir de ces étiquettes.

`analysis_session.py` contient toute la logique de décision appliquée à une
fenêtre. La boucle temps réel et les bancs de mesure l'utilisent tous les deux,
ce qui garantit que les chiffres publiés portent sur le système réellement
exécuté en séance et non sur une réimplémentation approchante.

## Installation

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python download_model.py
cp .env.example .env
```

Le premier démarrage télécharge le modèle vocal (~1 Go) depuis Hugging Face.

## Lancement

```bash
python -m api.main
```

## Reproduire les chiffres publiés

Aucun chiffre du mémoire n'a été estimé. Chacun sort d'une commande du dossier
`tools/`, exécutée sur le code de ce dépôt dans sa configuration par défaut. Cette
section donne la commande exacte pour chacun, de sorte qu'un tiers puisse refaire
la mesure et tomber sur la même valeur.

Toutes les commandes se lancent depuis `Projet/back`, environnement virtuel activé.

### Se procurer les corpus

Les corpus ne sont pas versionnés, ils pèsent trop lourd. Les étiquettes, elles, le
sont : `crema_labels.csv` et `crema_labels_strict.csv` sont dans le dépôt, ce qui
permet de retrouver exactement le même jeu d'évaluation.

```bash
# CREMA-D : reconstruire les étiquettes à partir des votes d'annotateurs
python -m tools.crema_incongruence --summary summaryTable.csv --out .

# puis ne télécharger que les clips étiquetés (~100 Mo au lieu de 7,5 Go)
python -m tools.crema_fetch --labels crema_labels.csv --repo ../../crema-d
```

RAVDESS se récupère sur https://zenodo.org/records/1188976. Un seul dossier
d'acteur suffit, `Actor_04` est celui qui a servi. Le décodage des noms de fichiers
est expliqué dans `tools/README.md`.

### Quelle commande donne quel chiffre

| Ce qui est publié | Commande |
|---|---|
| Près d'un enregistrement sur deux perçu différemment selon le canal, soit 3 678 dissonants contre 3 764 congruents sur 7 442 | `python -m tools.crema_incongruence --summary summaryTable.csv --out .` |
| Aire sous la courbe 0,808 et son intervalle, 227 extraits exploitables sur 344, distances médianes 1,155 et 0,588, arbitrage 0,80 contre 0,94 | `python -m tools.benchmark --labels crema_labels_strict.csv --media ../../crema-d --live` |
| Aire sous la courbe 0,639 sur le corpus entier, extraits ambigus compris | `python -m tools.benchmark --labels crema_labels.csv --media ../../crema-d --limit 400 --live` |
| Délai de 3,45 s dont 446 ms de calcul, part du modèle vocal supérieure à 99 %, budget visage utilisé à moins de 7 %, 1,5 Go de mémoire et 10 % du processeur | `python -m tools.latency --video ../../Video/generated_video.mp4 --windows 20 --captures 100` |
| Détection sur 268 des 344 fenêtres, taux par configuration d'émotions, répartition entre vigilance et vibration | `python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode croise --live` |
| Écart de 1,35 mesuré à travers la capture d'écran, huit alertes sur huit fenêtres | `python -m tools.selftest --video ../../Video/generated_video.mp4 --hud aucun --tours 8` |
| Le widget ne gêne pas, 1,29 contre 1,35 | `python -m tools.selftest --video ../../Video/generated_video.mp4 --hud widget --tours 8` |
| Le panneau de réglages annule la détection, huit alertes tombent à zéro et le modèle répond « neutre » à 87-94 % | `python -m tools.selftest --video ../../Video/generated_video.mp4 --hud parametres --tours 8` |
| Écart de 1,53 en lecture directe du fichier, d'où les 12 % que coûte l'acquisition par l'écran | `python -m tools.replay --video ../../Video/generated_video.mp4` |
| Caractérisation des clips de démonstration, celui à retenir et ceux à éviter | `python -m tools.replay --video ../../Video/<clip>.mp4`, un passage par clip |

### Tout enchaîner

```bash
python -m tools.crema_incongruence --summary summaryTable.csv --out .
python -m tools.benchmark --labels crema_labels_strict.csv --media ../../crema-d --live --csv mesures_cremad_strict.csv
python -m tools.benchmark --labels crema_labels.csv --media ../../crema-d --limit 400 --live --csv mesures_cremad_full.csv
python -m tools.latency  --video ../../Video/generated_video.mp4 --windows 20 --captures 100 --json mesures_latence.json
python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode croise --live --csv mesures_ravdess.csv
python -m tools.replay   --video ../../Video/generated_video.mp4
python -m tools.selftest --video ../../Video/generated_video.mp4 --hud aucun      --tours 8
python -m tools.selftest --video ../../Video/generated_video.mp4 --hud widget     --tours 8
python -m tools.selftest --video ../../Video/generated_video.mp4 --hud parametres --tours 8
```

Comptez une bonne heure. Les deux passages de `benchmark` sont les plus longs, ils
lancent une inférence vocale par extrait.

### Quatre précautions, sans lesquelles les chiffres ne veulent rien dire

**`--live` n'est pas optionnel.** Sans lui, les bancs cadrent les fenêtres sur les
passages parlés et autorisent le recouvrement, ce qui embellit les résultats sans
rien dire de l'usage réel. Le mode d'exploration existe pour comprendre le moteur,
jamais pour publier.

**L'intervalle de confiance ne se publie pas au-delà de deux décimales.** Il vient
d'un rééchantillonnage aléatoire, sa troisième décimale bouge d'une exécution à
l'autre.

**La latence se mesure trois fois.** Les temps d'inférence dépendent de l'état
thermique du processeur. Un passage unique décrit un instant, pas un régime, et
c'est l'étendue observée qu'il faut rapporter.

**`selftest` prend la main sur l'écran et sur le son.** Il ouvre une fenêtre et
joue la bande son sur la sortie par défaut. Toute fenêtre passant par-dessus serait
analysée à la place de la vidéo, il ne faut donc rien faire d'autre pendant la
mesure.

### Avant une démonstration

```bash
python -m tools.preflight                 # dépendances, modèles, configuration, audio, montre
python -m tools.preflight --sans-ble      # si la montre n'est pas allumée
```

Si rien ne se détecte en séance alors que les bancs hors ligne détectent, la cause
est presque toujours dans les deux entrées que les bancs ne touchent pas, les pixels
et le loopback.

```bash
python -m tools.diagnose --zone 100,100,800,600     # le chemin visuel
python -m tools.diagnose --audio                    # le chemin sonore
```

Le détail de chaque outil, ses options et les limites de chaque corpus sont dans
`tools/README.md`.

## Configuration

Tous les réglages sont documentés dans `.env.example`. Les plus structurants :

| Variable | Défaut | Rôle |
|---|---|---|
| `ANALYSIS_WINDOW_SECONDS` | 3.0 | Fenêtre commune aux deux canaux |
| `FACE_SAMPLE_INTERVAL` | 0.35 | Cadence d'échantillonnage du visage |
| `FACE_MIN_SAMPLES` | 3 | Images minimum pour exploiter une fenêtre |
| `FACE_MAX_DISPERSION` | 0.45 | Au-delà, le visage est jugé trop instable |
| `VOICE_SUBWINDOWS` | 3 | Sous-fenêtres vocales recouvrantes |
| `VOICE_CONFIDENCE_MODE` | `stabilite` | `stabilite` ou `intensite` (ancien) |
| `EMOTIEFFLIB_VA_GAIN` | 1.8 | Harmonisation d'échelle inter-canaux |
| `SEUIL_DISSONANCE_DISTANCE` | 0.8 | Distance de déclenchement |
| `ALERT_MODERATE_DISTANCE` | 1.5 | Passage en niveau MODERATE |
| `ALERT_SEVERE_DISTANCE` | 1.8 | Passage en niveau SEVERE |
| `PERSISTENCE_MIN` | 1 | Fenêtres dissonantes exigées avant la vibration |
| `VIBRATION_COOLDOWN_SECONDS` | 5 | Délai réfractaire entre deux vibrations |
| `FACE_VETO_MODE` | `desactive` | Confrontation cross-modale |

Les distances se lisent sur une échelle allant de 0 à 2,83, ce dernier chiffre
étant la diagonale du carré [-1, 1] × [-1, 1] du plan de Russell.

### Harmonisation d'échelle et calibration

La régression AffectNet est calibrée mais resserrée (dépasse rarement ±0.5), là
où le canal vocal couvre pratiquement [−1, 1]. Sans `EMOTIEFFLIB_VA_GAIN`, la
distance entre les deux points serait dominée par la voix. **Ce n'est pas un
réglage de sensibilité mais un changement d'unité**, qui doit être mesuré et non
deviné.

`GET /calibration` renvoie les distributions réellement observées sur les deux
canaux (percentiles de valence, d'arousal et de magnitude) et propose une valeur
de gain harmonisant les amplitudes. Laisser tourner une session de plusieurs
minutes sur du matériel représentatif, puis lire l'endpoint.

### Confrontation cross-modale, désactivée et pourquoi

`FACE_VETO_MODE` était introduit pour compenser un défaut du moteur FER, qui
confondait *happy* et *sad* : quand la voix contredisait un label facial peu
confiant, on supposait une erreur de classification. Depuis le passage à
EmotiEffLib, le point facial ne dérive plus d'un label mais d'une régression, et
ce raisonnement ne s'applique plus.

Surtout, le mécanisme est **circulaire** : il utilise le désaccord entre les deux
canaux comme critère pour disqualifier l'un d'eux, alors que ce désaccord est
précisément l'objet de la mesure. La fiabilité de chaque canal est désormais
estimée *à l'intérieur* de ce canal, par la dispersion intra-fenêtre côté visage
et la concordance des sous-fenêtres côté voix, jamais par comparaison avec l'autre.

Les modes `penalite` et `rejet` restent activables pour mesurer leur effet sur un
même corpus.

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| WS | `/ws` | Flux temps réel avec le frontend |
| GET | `/health` | État de l'API, du BLE, latence du dernier write GATT |
| GET | `/calibration` | Distributions observées et gain d'échelle suggéré |
| POST | `/ble/connect` · `/ble/disconnect` | Connexion / déconnexion de la montre |
| GET | `/ble/status` | État de la connexion BLE |
| GET | `/audio/devices` | Liste des périphériques loopback |
| GET | `/audio/test` | Mesure du niveau sonore capté |
| POST | `/audio/device` | Choix du périphérique loopback (persisté dans `.env`) |

### Messages WebSocket entrants

| Message | Effet |
|---|---|
| `{"x":…, "y":…, "w":…, "h":…}` | Met à jour la zone d'écran capturée |
| `{"type": "test_vibration"}` | Déclenche une vibration de test |
| `{"type": "reset_context"}` | Purge la mémoire des deux canaux |

## Plan de Russell

Les quadrants sont déduits du **point mesuré**, pas du label :

- **Q1 (Actif/Positif)** : valence ≥ 0, arousal ≥ 0
- **Q2 (Calme/Positif)** : valence ≥ 0, arousal < 0
- **Q3 (Passif/Négatif)** : valence < 0, arousal < 0
- **Q4 (Actif/Négatif)** : valence < 0, arousal ≥ 0
- **Q5 (Neutre)** : voisinage de l'origine

## Limites connues

- La valeur transmise sous le nom `confidence` n'est pas une probabilité que la
  dissonance existe : c'est le produit de la fiabilité moyenne des deux canaux
  par le degré d'incongruence. Cette moyenne étant pondérée, elle est dominée
  par le canal le plus fiable, alors qu'une comparaison est bornée par son
  maillon le plus faible.
- `FACE_MIN_CONFIDENCE` et `FACE_MIN_MARGIN` ont été réglés sur les 7 classes de
  l'ancien moteur ; ils n'ont pas été revalidés sur les 8 classes d'AffectNet.
- Aucun corpus public n'annote la *dissonance* entre canaux. Un jeu étiqueté a
  donc été dérivé de CREMA-D, en exploitant le fait que ses annotateurs ont noté
  séparément l'image et le son. Les seuils ont été confrontés à ce jeu, et le seuil
  retenu n'est pas l'optimum mesuré : 0,80 privilégie délibérément la sensibilité
  sur la précision, là où 0,94 équilibrerait les deux. Ce jeu reste un dérivé, il
  ne contient pas de dissonance clinique authentique.
- L'image analysée est une recapture d'écran, donc doublement compressée.

## Technologies

FastAPI · MediaPipe · EmotiEffLib (ONNX Runtime) · PyTorch / Transformers
(wav2vec2) · librosa · soundcard · mss · bleak · OpenCV · NumPy · Pillow
