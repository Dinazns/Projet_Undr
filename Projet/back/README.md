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
├── download_model.py        # Téléchargement du modèle MediaPipe
├── .env.example             # Configuration de référence
└── requirements.txt
```

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
- Les seuils de gradation n'ont pas été calibrés sur un corpus annoté : il
  n'existe pas de corpus public annoté en *dissonance* entre canaux.
- L'image analysée est une recapture d'écran, donc doublement compressée.

## Technologies

FastAPI · MediaPipe · EmotiEffLib (ONNX Runtime) · PyTorch / Transformers
(wav2vec2) · librosa · soundcard · mss · bleak · OpenCV · NumPy · Pillow
