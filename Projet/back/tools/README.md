# Bancs de mesure hors ligne

Font tourner la chaîne d'analyse réelle sur des fichiers vidéo, sans HUD, sans
Electron et sans capture d'écran. La logique de décision est celle de
`services/analysis_session.py`, la même qu'en séance : les chiffres obtenus ici
portent donc sur le système effectivement exécuté, pas sur une réimplémentation.

## Les outils en un coup d'œil

| Outil | Répond à la question |
|---|---|
| `benchmark.py` | Le dispositif distingue-t-il un enregistrement dissonant d'un congruent ? |
| `evaluate_corpus.py` | Quelles configurations d'émotions repère-t-il, lesquelles lui échappent ? |
| `latency.py` | Combien de temps le praticien attend-il, et où part le temps de calcul ? |
| `replay.py` | Que déciderait le dispositif, fenêtre par fenêtre, sur cette vidéo ? |
| `selftest.py` | Que coûte la chaîne d'acquisition réelle, écran et loopback compris ? |
| `diagnose.py` | Pourquoi ne détecte-t-il rien en séance, et laquelle des deux entrées est en cause ? |
| `preflight.py` | Tout est-il en place avant une démonstration ? |
| `crema_incongruence.py` | Construit le jeu étiqueté à partir des votes de CREMA-D |
| `crema_fetch.py` | Récupère les seuls médias nécessaires, sans les 7,5 Go du corpus |
| `make_demo_reel.py` | Monte une vidéo de démonstration à partir d'un corpus étiqueté |

`evaluate_corpus.py` fournit les briques communes, les autres bancs l'importent.
Le supprimer casserait l'ensemble.

## Prérequis

```bash
pip install -r requirements.txt
pip install imageio-ffmpeg      # si ffmpeg n'est pas déjà sur le PATH
```

## Corpus

Conçu pour **RAVDESS** (Livingstone & Russo, 2018, https://zenodo.org/records/1188976),
dont la nomenclature de fichiers porte l'étiquette d'émotion :

```
01-01-06-01-02-01-12.mp4
 |  |  |  |  |  |  +-- acteur (impair = homme, pair = femme)
 |  |  |  |  |  +----- répétition
 |  |  |  |  +-------- phrase
 |  |  |  +----------- intensité (01 normale, 02 forte)
 |  |  +-------------- émotion (01 neutre … 08 surprise)
 |  +----------------- canal vocal (01 parole)
 +-------------------- modalité (01 audio+vidéo, 02 vidéo seule, 03 audio seul)
```

**Les fichiers de modalité 02 sont ignorés** : leur piste audio existe mais elle
est vide, aucune fenêtre ne serait exploitable. Sur un dossier d'acteur complet,
la moitié des fichiers est donc écartée automatiquement.

## Ce que mesure ce corpus, concrètement

Mesures relevées sur `Actor_04` (120 fichiers) avant toute évaluation :

| Constat | Valeur | Conséquence |
|---|---|---|
| Fichiers de modalité 02 | 60 sur 120 | Piste audio vide : **ignorés automatiquement**, il reste 60 clips |
| Durée d'un extrait | médiane 3,58 s | Une fenêtre de 3 s ne laisse qu'un seul point de mesure |
| Silence en tête | médiane 1,10 s | |
| Silence en queue | médiane 1,20 s | |
| **Parole utile** | **médiane 1,28 s** | Plus courte que la fenêtre d'analyse par défaut |
| Côté du crop de visage à 448 px | médiane 191 px | Très au-dessus de `FACE_MIN_SIZE_PX` (64) : aucun rejet géométrique |

Ces contraintes ouvrent deux façons de mesurer, qui ne répondent pas à la même
question et ne doivent jamais être mélangées dans un rapport.

### `--live`, le mode à utiliser pour publier un chiffre

C'est le mode de référence, et celui qui a produit tous les chiffres du mémoire.
Il reproduit la boucle d'`api/main.py` sans le moindre aménagement : fenêtres de
`ANALYSIS_WINDOW_SECONDS` qui se suivent sans recouvrement depuis le début de
l'extrait, aucun recalage sur les passages parlés, aucune dégradation ajoutée, et
décision prise sur la première fenêtre exploitable plutôt que sur la meilleure.

```bash
python -m tools.benchmark --labels crema_labels_strict.csv --media ../../crema-d --live
python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode croise --live
```

L'option écrase toute option contraire, délibérément : un banc annoncé « live »
avec un réglage d'évaluation resté actif produirait des chiffres impossibles à
interpréter. Le prix à payer est un taux de rejet élevé, environ un tiers des
extraits ne produisant aucune fenêtre exploitable sur ces corpus courts. Ce rejet
fait partie du résultat et doit être rapporté avec lui.

### Le mode d'exploration, pour comprendre plutôt que pour publier

Sans `--live`, le banc cadre les fenêtres sur le segment parlé, autorise le
recouvrement et raccourcit la fenêtre. Cela sert à observer le comportement du
moteur sur des extraits trop brefs pour la configuration réelle, jamais à
annoncer une performance.

```bash
python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode croise \
    --window 1.5 --hop 0.3 --degrade
```

Une fenêtre raccourcie oblige à ajuster le découpage vocal.
`VOICE_SUBWINDOW_MIN_SECONDS` vaut 1,0 s : dans une fenêtre de 1,5 s, une seule
sous-fenêtre tient, la fiabilité par concordance devient impossible et le service
retombe silencieusement sur l'ancien mode « intensité ». Le banc le signale, mais
mieux vaut le prévenir :

```bash
# Windows PowerShell
$env:VOICE_SUBWINDOW_MIN_SECONDS="0.4"
```

Tout chiffre issu de ce mode doit préciser sa configuration, faute de quoi il
n'est pas comparable à celui du mode `--live`.

## Les deux modes

### `--mode congruence` | mesure de la spécificité

Chaque clip est joué tel quel. Dans RAVDESS, le comédien exprime la **même**
émotion sur le visage et dans la voix : les deux canaux sont congruents. Toute
alerte est donc un **faux positif**, et le taux d'alerte mesure directement le
bruit du dispositif.

```bash
python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode congruence \
    --window 1.5 --hop 0.3 --no-warmup --degrade --csv congruence.csv
```

### `--mode croise` | mesure de la sensibilité

Le visage d'un clip est associé à la bande son d'un autre clip du même acteur et
de la même phrase, mais de valence opposée : visage joyeux sur voix triste, et
réciproquement. On obtient une **dissonance de synthèse à vérité terrain
connue**.

C'est ce qui comble le manque identifié dans l'état de l'art : les corpus
publics annotent une émotion congruente par extrait, aucun n'annote une
incongruence *entre* canaux. Le protocole ci-dessus en fabrique un à partir d'un
corpus existant, reproductible par un tiers.

```bash
python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode croise \
    --window 1.5 --hop 0.3 --no-warmup --degrade --limit 60 --csv croise.csv
```

### `--degrade`

Ajoute un aller-retour JPEG (qualité 55) pour approcher la dégradation d'un flux
de visioconférence. Sans lui, les mesures portent sur des images de studio et
surestiment les performances. À passer dans les deux modes pour obtenir un
chiffre transposable aux conditions d'usage.

## Lecture des résultats

Le mode `congruence` donne un taux de faux positifs, le mode `croise` un taux de
détection, sur les mêmes réglages. Les faire varier ensemble en changeant
`SEUIL_DISSONANCE_DISTANCE` dans le `.env` trace le compromis entre les deux :
c'est la courbe qui permet de choisir un seuil sur des données plutôt qu'au
jugé. Le CSV contient une ligne par fenêtre, avec la distance mesurée, pour
refaire l'analyse sans relancer les inférences.

## `benchmark.py` | les chiffres du mémoire

`evaluate_corpus.py` mesure un taux d'alerte par mode. `benchmark.py` va plus
loin : il construit un **jeu étiqueté** et en sort une matrice de confusion, un
balayage de seuil et un point de fonctionnement.

```bash
python -m tools.benchmark --corpus ../../Actor_04 --degrade --csv benchmark.csv
```

Construction du jeu, à partir des seuls fichiers déjà présents :

| Classe | Construction | Effectif sur un dossier d'acteur |
|---|---|---|
| **Négatifs**, pas de dissonance | Clips tels quels : le comédien joue la même émotion sur les deux canaux | 60 |
| **Positifs**, dissonance | Visage d'un clip + bande son d'un autre clip, même acteur, même phrase, valence opposée | jusqu'à 60 |

C'est le protocole de **recombinaison intermodale**, employé de longue date en
psychologie de la perception multimodale pour fabriquer des stimuli incongruents
à vérité terrain connue. C'est aussi, dans son principe, celui de SASE-FE :
induire une émotion chez un sujet et lui en faire exprimer une autre.

L'inférence n'est lancée **qu'une fois**. La distance mesurée entre les deux
canaux ne dépend pas du seuil de décision : celui-ci est donc balayé en
post-traitement, ce qui donne tout le compromis sensibilité/spécificité pour le
prix d'une seule passe. Le script imprime le seuil optimal à reporter dans le
`.env`.

Les repères affichés en fin de rapport viennent du *ChaLearn LAP Real vs. Fake
Expressed Emotion Challenge* (ICCV 2017) sur la tâche « expression authentique
ou feinte » : hasard 50 %, **observateurs humains 54,5 %**, meilleure équipe
67 %. Ils situent un ordre de grandeur, la tâche et le corpus étant différents, et ne
constituent pas une comparaison de mesures équivalentes. À déclarer comme tel.

### Les deux façons d'obtenir un jeu étiqueté

`benchmark.py` accepte deux sources, qui n'ont pas la même valeur scientifique.

**`--corpus`, appariement croisé (montage).** Les positifs sont fabriqués :
visage d'un clip, bande son d'un autre. Avantage : disponible immédiatement à
partir de RAVDESS. **Limite sérieuse à déclarer** : ce n'est pas ainsi qu'une
dissonance se présente en situation réelle. Le montage désynchronise les lèvres,
casse la respiration, supprime la cohérence temporelle entre le geste et la
prosodie. Le dispositif y est aveugle, il ne compare que deux points dans le
plan de Russell, mais un jury peut objecter, à raison, que les positifs sont
des artefacts. La recombinaison intermodale reste une méthode admise en
psychologie de la perception multimodale ; elle mesure la capacité à repérer un
écart entre deux canaux, pas à repérer une dissonance authentique.

**`--labels`, enregistrements réels non modifiés (recommandé).** Chaque clip
est un enregistrement unique, avec son propre son, sa propre synchronisation
labiale, sa propre respiration. **Rien n'est monté.** L'étiquette vient d'un
jugement extérieur.

Sur CREMA-D, cette étiquette est fournie par le protocole d'annotation lui-même :
chaque clip a été noté séparément par des humains en condition « voix seule » et
en condition « visage seul ». Quand `VoiceVote != FaceVote`, des annotateurs ont
perçu une émotion dans la voix et une autre sur le visage **du même
enregistrement authentique**. C'est une dissonance naturelle, attestée par
jugement humain, sans aucune manipulation du signal.

```bash
# 1. étiquettes, ne nécessite que les CSV du dépôt, quelques Mo
python -m tools.crema_incongruence --summary summaryTable.csv --out .

# 2. téléchargement des seuls clips étiquetés (~100 Mo au lieu de 7,5 Go)
python -m tools.crema_fetch --labels crema_labels.csv --out crema_media

# 3. mesure sur les enregistrements réels
python -m tools.benchmark --labels crema_labels.csv --media crema_media --degrade
```

`--media` accepte l'arborescence de CREMA-D telle quelle (`VideoFlash/` pour la
vidéo, `AudioWAV/` pour le son) ou un dossier plat.

### Où sont les vidéos de CREMA-D

Deux distributions trompeuses circulent :

- **le miroir Kaggle** ne publie que le dossier `AudioWAV` : aucune vidéo ;
- **le ZIP du dépôt** (~24 Mo) ne contient que des pointeurs git-lfs à la place
  des médias, des fichiers de quelques centaines d'octets qui ne s'ouvrent pas.

Les clips audio + image sont dans `VideoFlash/*.flv`. Trois façons de les avoir :

| Méthode | Volume | Durée |
|---|---|---|
| `tools/crema_fetch.py` (seulement les clips étiquetés) | ~100 Mo | quelques minutes |
| `git lfs clone` du miroir GitLab | 7,5 Go | ~1 h |
| `git lfs pull -I "VideoFlash/*"` après un clone sans médias | ~5 Go | ~40 min |

Si OpenCV n'ouvre pas les `.flv`, une conversion unique suffit :

```bash
ffmpeg -i VideoFlash/NOM.flv -c:v libx264 -c:a aac VideoFlash/NOM.mp4
```

## `latency.py` | combien de temps le praticien attend

`benchmark.py` dit si le dispositif détecte. `latency.py` dit en combien de temps.

```bash
python -m tools.latency --video ../../Video/generated_video.mp4 --windows 40 --csv latence.csv
```

Aucune modification du code de production : l'outil enveloppe à chaud les méthodes réellement
appelées en séance dans un compteur, si bien que le logiciel mesuré est le logiciel livré. Les
premières mesures sont écartées (`--warmup`, 3 par défaut), la première inférence d'un modèle
ONNX allouant ses tampons et coûtant plusieurs fois le régime établi.

**Deux régimes à ne pas confondre dans la lecture du rapport.** La boucle d'analyse échantillonne
le visage *pendant* que le micro enregistre. Le coût de la chaîne faciale est donc amorti dans la
fenêtre et ne s'ajoute au délai que s'il dépasse `FACE_SAMPLE_INTERVAL` : l'outil vérifie cette
condition explicitement. Ce qui s'ajoute au délai est uniquement ce qui suit la fermeture de la
fenêtre, à savoir l'agrégation du visage, l'inférence vocale, la fusion et l'écriture BLE. C'est
ce total que le rapport appelle *chemin critique*.

**Variabilité entre exécutions.** Les temps d'inférence dépendent de l'état thermique et du
niveau d'accélération du processeur. Un seul passage ne suffit donc pas : enchaîner trois
exécutions et rapporter l'étendue observée, sinon le chiffre publié décrit un instant plutôt
qu'un régime.

| Option | Effet |
|---|---|
| `--windows` | Nombre de fenêtres chronométrées |
| `--captures` | Nombre de captures d'écran chronométrées |
| `--region` | Zone HUD à capturer, au format `x,y,largeur,hauteur` |
| `--ble` | Mesure aussi l'écriture GATT. Exige la montre allumée et appairée |
| `--json` / `--csv` | Sorties exploitables, matériel et configuration compris |

L'étape BLE mesure le seul write GATT, pas la durée du motif de vibration. Comme l'écriture se
fait **sans accusé de réception**, le chiffre relevé est le temps de remise du paquet à la pile
Bluetooth du système, non un aller-retour jusqu'à la montre : c'est une borne inférieure, à
déclarer comme telle.

## `replay.py` | rejouer une séance fenêtre par fenêtre

Là où les bancs précédents agrègent un corpus, celui-ci rejoue **une** vidéo dans
les conditions exactes du direct et imprime la trace que le praticien aurait vue
défiler. Une seule session pour tout le rejeu, avec sa mémoire, ses purges de
contexte et son délai réfractaire. L'horloge est simulée, sans quoi un rejeu plus
rapide que le temps réel ferait tomber toutes les fenêtres dans le même
intervalle réfractaire et supprimerait des vibrations réellement dues.

```bash
python -m tools.replay --video ../../Video/generated_video.mp4
```

## `selftest.py` | ce que coûte la chaîne d'acquisition

Seul banc du dépôt qui exerce la chaîne complète, les pixels de l'écran et le son
du haut-parleur compris. Il joue la vidéo dans une fenêtre, envoie sa bande son
sur la sortie par défaut, puis analyse cette fenêtre comme le ferait la boucle
réelle. Comparer sa trace à celle de `replay.py` sur le même fichier isole en une
lecture ce que l'acquisition dégrade.

L'option `--hud` superpose les calques de l'interface sur la vidéo, ce qui permet
de mesurer leur effet. Le panneau de réglages ouvert efface l'expression du
visage et fait tomber la détection à zéro : à vérifier avant toute démonstration.

```bash
python -m tools.selftest --video ../../Video/generated_video.mp4 --hud aucun
python -m tools.selftest --video ../../Video/generated_video.mp4 --hud parametres
```

Ouvre une fenêtre et joue du son. Ne rien faire d'autre pendant la mesure, toute
fenêtre passant par-dessus serait analysée à la place de la vidéo.

## `diagnose.py` | pourquoi rien ne se détecte en séance

Quand le banc hors ligne trouve une dissonance et que la séance n'en trouve
aucune, la cause est presque toujours dans les deux entrées que le banc ne touche
jamais, les pixels et le loopback. Cet outil les teste séparément, puis ensemble.

```bash
python -m tools.diagnose --zone 100,100,800,600     # le chemin visuel
python -m tools.diagnose --audio                    # le chemin sonore
python -m tools.diagnose --zone 100,100,800,600 --seance 60
```

## `preflight.py` | contrôle avant démonstration

Vérifie dans l'ordre les dépendances, les modèles, la cohérence de la
configuration, le périphérique audio et la montre. À lancer la veille, puis juste
avant de passer.

```bash
python -m tools.preflight
python -m tools.preflight --sans-ble      # si la montre n'est pas allumée
```

## Options

| Option | Effet |
|---|---|
| `--live` | Conditions du direct. À utiliser pour tout chiffre publié |
| `--window` | Durée de la fenêtre d'analyse (défaut : celle du `.env`) |
| `--hop` | Pas entre deux fenêtres (défaut : moitié de la fenêtre) |
| `--no-warmup` | N'ignore pas la première fenêtre de chaque clip. Justifié ici : le banc crée une session neuve par clip, donc aucune mémoire d'une scène précédente ne peut contaminer la première fenêtre. Le garde-fou n'a rien à protéger et coûterait la totalité des mesures sur des extraits courts. |
| `--degrade` | Compression JPEG à 55 pour approcher un flux de visioconférence |
| `--limit` | Nombre de clips (congruence) ou de paires (croisé) |
| `--csv` | Une ligne par fenêtre, avec la distance mesurée |

## Limites à déclarer

- Les émotions de RAVDESS sont **jouées** par des comédiens, en studio, sur deux
  phrases neutres et sans compression de visioconférence. Elles ne préjugent pas
  du comportement du dispositif sur des expressions spontanées en
  téléconsultation.
- La dissonance de synthèse du mode croisé n'est pas une dissonance clinique :
  c'est le montage de deux expressions jouées séparément, sans la cohérence
  temporelle d'un masquage réel.
- Un dossier d'acteur unique ne dit rien de la robustesse aux carnations, aux
  âges et aux éclairages : évaluer sur plusieurs acteurs avant toute conclusion.
