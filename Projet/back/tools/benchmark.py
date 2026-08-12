"""
Banc de mesure : sensibilité, spécificité et seuil optimal.

Construit un jeu ÉTIQUETÉ à partir d'un corpus RAVDESS déjà présent sur le
disque, puis mesure les performances du dispositif dessus.

    Négatifs (« pas de dissonance ») : les clips tels quels. L'acteur joue la
        même émotion sur le visage et dans la voix : les deux canaux sont
        congruents par construction.

    Positifs (« dissonance ») : le visage d'un clip associé à la bande son d'un
        autre clip du même acteur, même phrase, valence opposée. La personne
        « exprime » une émotion tout en « sonnant » l'émotion inverse.

C'est le protocole de recombinaison intermodale, utilisé de longue date en
psychologie de la perception multimodale pour fabriquer des stimuli incongruents
à vérité terrain connue. C'est aussi, dans son principe, celui de SASE-FE :
induire une émotion chez un sujet et lui en faire exprimer une autre.

L'inférence n'est lancée QU'UNE FOIS. Le seuil de décision est ensuite balayé en
post-traitement, la distance mesurée entre les deux canaux ne dépendant pas du
seuil : on obtient le compromis sensibilité/spécificité complet pour le prix
d'une seule passe.

    python -m tools.benchmark --corpus ../../Actor_04 --degrade --csv benchmark.csv
"""
import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (  # noqa: E402
    ANALYSIS_WINDOW_SECONDS,
    CAPTURE_MAX_SIZE,
    FACE_SAMPLE_INTERVAL,
    VOICE_SUBWINDOW_MIN_SECONDS,
)
from tools.evaluate_corpus import (  # noqa: E402
    build_opposite_pairs, evaluate_pair, find_clips, load_audio,
)

# Repères publiés sur la tâche « expression authentique ou feinte »
# (ChaLearn LAP Real vs. Fake Expressed Emotion Challenge, ICCV 2017).
REPERE_HASARD = 50.0
REPERE_HUMAIN = 54.5
REPERE_ETAT_ART = 67.0


def score_clip(rows, agregation="max"):
    """
    Résume un clip par une seule valeur, à partir de ses fenêtres.

    "max" : la plus grande distance observée. Correspond à l'usage visé, où une
        alerte n'a pas besoin de tenir toute la séance pour être utile, mais
        avantage mécaniquement les clips qui produisent beaucoup de fenêtres.

    "premiere" : la distance de la PREMIÈRE fenêtre exploitable. C'est ce que le
        dispositif décide réellement en séance sur un extrait de cette durée,
        sans le bénéfice d'un choix a posteriori parmi plusieurs fenêtres.
    """
    distances = [r["distance"] for r in rows if r["evaluee"]]
    if not distances:
        return None, 0
    if agregation == "premiere":
        return distances[0], len(distances)
    return max(distances), len(distances)


def collect(clips, degrade, window, hop, limit, seed):
    """Renvoie [(nom, label, score, n_fenetres, emotions)] pour les deux classes."""
    echantillons = []

    negatifs = clips[:limit] if limit else clips
    for i, clip in enumerate(negatifs, 1):
        print("  negatif  [%3d/%d] %s" % (i, len(negatifs), os.path.basename(clip.path)), flush=True)
        rows = evaluate_pair(clip.path, load_audio(clip.path), degrade, window, hop, 0)
        score, n = score_clip(rows)
        echantillons.append((os.path.basename(clip.path), 0, score, n, clip.emotion))

    paires = build_opposite_pairs(clips, limit or len(negatifs), seed)
    for i, (face_clip, voice_clip) in enumerate(paires, 1):
        nom = "%s+%s" % (os.path.basename(face_clip.path)[:-4],
                         os.path.basename(voice_clip.path)[:-4])
        print("  positif  [%3d/%d] visage=%s voix=%s"
              % (i, len(paires), face_clip.emotion, voice_clip.emotion), flush=True)
        rows = evaluate_pair(face_clip.path, load_audio(voice_clip.path), degrade, window, hop, 0)
        score, n = score_clip(rows)
        echantillons.append((nom, 1, score, n, "%s/%s" % (face_clip.emotion, voice_clip.emotion)))

    return echantillons


def resoudre_media(nom, racine):
    """
    Retrouve la vidéo et l'audio d'un clip à partir de son nom.

    Gère l'arborescence de CREMA-D (VideoFlash/ + AudioWAV/) comme un dossier
    plat. L'audio est pris dans le WAV lorsqu'il existe : c'est la piste que les
    auteurs fournissent pour le traitement automatique, et elle évite de
    redécoder le conteneur vidéo.
    """
    base = os.path.splitext(nom)[0]
    video = None
    for sous, ext in (("VideoFlash", ".flv"), ("", ".flv"), ("", ".mp4"), ("VideoMP4", ".mp4")):
        cand = os.path.join(racine, sous, base + ext) if sous else os.path.join(racine, base + ext)
        if os.path.exists(cand):
            video = cand
            break
    audio = None
    for sous, ext in (("AudioWAV", ".wav"), ("", ".wav")):
        cand = os.path.join(racine, sous, base + ext) if sous else os.path.join(racine, base + ext)
        if os.path.exists(cand):
            audio = cand
            break
    return video, (audio or video)


def collect_etiquetes(labels_csv, racine, degrade, window, hop, limit,
                      align_speech=True, agregation="max", warmup=0):
    """
    Évalue des enregistrements RÉELS et non modifiés, à partir d'un fichier
    d'étiquettes externe.

    Aucun montage : chaque clip est un enregistrement unique, avec son propre
    son, sa propre synchronisation labiale et sa propre respiration. L'étiquette
    vient d'un jugement extérieur. Dans CREMA-D, c'est le désaccord entre les
    annotateurs ayant noté la voix seule et ceux ayant noté le visage seul sur
    le même enregistrement.
    """
    with open(labels_csv, newline="", encoding="utf-8") as f:
        lignes = [r for r in csv.DictReader(f) if r.get("clip")]
    if limit:
        pos = [r for r in lignes if str(r["label"]).strip() == "1"][:limit]
        neg = [r for r in lignes if str(r["label"]).strip() != "1"][:limit]
        lignes = pos + neg

    echantillons, manquants = [], 0
    for i, r in enumerate(lignes, 1):
        nom, label = r["clip"].strip(), int(str(r["label"]).strip())
        video, audio = resoudre_media(nom, racine)
        if not video:
            manquants += 1
            continue
        print("  [%4d/%d] %-28s label=%d" % (i, len(lignes), nom, label), flush=True)
        rows = evaluate_pair(video, load_audio(audio), degrade, window, hop, warmup,
                             align_speech)
        score, n = score_clip(rows, agregation)
        echantillons.append((nom, label, score, n, ""))
    if manquants:
        print("  %d clip(s) introuvable(s) sous %s" % (manquants, racine))
    return echantillons


def matrice(echantillons, seuil):
    tp = fp = tn = fn = 0
    for _, label, score, _n, _e in echantillons:
        if score is None:
            continue
        predit = 1 if score >= seuil else 0
        if label == 1 and predit == 1:
            tp += 1
        elif label == 1 and predit == 0:
            fn += 1
        elif label == 0 and predit == 1:
            fp += 1
        else:
            tn += 1
    return tp, fp, tn, fn


def metriques(tp, fp, tn, fn):
    sens = tp / max(tp + fn, 1)
    spec = tn / max(tn + fp, 1)
    prec = tp / max(tp + fp, 1)
    f1 = 2 * prec * sens / max(prec + sens, 1e-9)
    return sens, spec, (sens + spec) / 2, prec, f1


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", default=None,
                   help="dossier RAVDESS : jeu construit par appariement croisé")
    p.add_argument("--labels", default=None,
                   help="CSV clip,label : évalue des enregistrements réels non modifiés")
    p.add_argument("--media", default=None,
                   help="racine des fichiers média associés à --labels")
    p.add_argument("--limit", type=int, default=None, help="clips par classe")
    p.add_argument("--degrade", action="store_true",
                   help="compression JPEG pour approcher un flux de visioconference")
    p.add_argument("--window", type=float, default=1.5)
    p.add_argument("--hop", type=float, default=0.3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-align-speech", action="store_true",
                   help="ne recale PAS les fenetres sur le segment parle : c'est le "
                        "comportement reel du dispositif")
    p.add_argument("--agregation", choices=("max", "premiere"), default="max",
                   help="max : plus grande distance du clip. premiere : distance de la "
                        "premiere fenetre exploitable, ce que le dispositif decide "
                        "reellement en seance.")
    p.add_argument("--live", action="store_true",
                   help="mode fidele : reproduit la boucle d'api.main. Fenetres de "
                        "ANALYSIS_WINDOW_SECONDS qui se suivent, depuis t=0, sans "
                        "recalage sur la parole ni degradation ajoutee, decision prise "
                        "sur la premiere fenetre exploitable. Ecrase les options "
                        "contraires.")
    p.add_argument("--csv", default=None)
    args = p.parse_args()

    if not args.corpus and not args.labels:
        p.error("indiquez --corpus (appariement croise) ou --labels (enregistrements reels)")

    if args.live:
        args.window = ANALYSIS_WINDOW_SECONDS
        args.hop = ANALYSIS_WINDOW_SECONDS
        args.degrade = False
        args.no_align_speech = True
        args.agregation = "premiere"
        print()
        print("  MODE FIDELE : conditions de la boucle d'analyse reelle.")
        print("  Aucun amenagement de corpus : ni recalage sur la parole, ni fenetres")
        print("  recouvrantes, ni choix a posteriori parmi plusieurs fenetres.")
        print("  Sous-fenetre vocale minimale : %.1f s (valeur de production)."
              % VOICE_SUBWINDOW_MIN_SECONDS)
        if VOICE_SUBWINDOW_MIN_SECONDS * 2 > args.window:
            print("  ATTENTION : deux sous-fenetres vocales n'entrent pas dans %.1f s ;"
                  % args.window)
            print("  la fiabilite par concordance sera impossible.")
        print()

    align_speech = not args.no_align_speech
    warmup = None if args.live else 0

    print("  fenetre %.1f s | pas %.1f s | image toutes les %.2f s | capture %d px%s | %s"
          % (args.window, args.hop, FACE_SAMPLE_INTERVAL, CAPTURE_MAX_SIZE,
             " | degradation JPEG" if args.degrade else "",
             "recale sur la parole" if align_speech else "sans recalage"))
    print("  agregation par clip : %s" % args.agregation)

    if args.labels:
        racine = args.media or os.path.dirname(os.path.abspath(args.labels))
        print("Etiquettes : %s" % os.path.abspath(args.labels))
        print("Media      : %s" % os.path.abspath(racine))
        print("  Mode enregistrements REELS : aucun montage, chaque clip est un")
        print("  enregistrement unique avec sa propre synchronisation.")
        print()
        ech = collect_etiquetes(args.labels, racine, args.degrade,
                                args.window, args.hop, args.limit,
                                align_speech, args.agregation, warmup)
    else:
        clips, silencieux = find_clips(args.corpus)
        print("Corpus : %s" % os.path.abspath(args.corpus))
        print("  %d clip(s) exploitables, %d ignore(s) (piste audio vide)"
              % (len(clips), len(silencieux)))
        if not clips:
            return 1
        print("  Mode APPARIEMENT CROISE : les positifs sont des montages")
        print("  (visage d'un clip + voix d'un autre). Voir les limites dans le README.")
        print()
        ech = collect(clips, args.degrade, args.window, args.hop, args.limit, args.seed)

    if not ech:
        print("Aucun clip evalue.")
        return 1

    exploitables = [e for e in ech if e[2] is not None]
    pos = [e for e in exploitables if e[1] == 1]
    neg = [e for e in exploitables if e[1] == 0]

    print()
    print("=" * 78)
    print("JEU ETIQUETE")
    print("=" * 78)
    print("  %d clip(s) construits, %d exploitable(s)" % (len(ech), len(exploitables)))
    print("  %d dissonances (positifs)  |  %d congruents (negatifs)" % (len(pos), len(neg)))
    if not pos or not neg:
        print("  Une classe est vide : impossible de calculer quoi que ce soit.")
        return 1

    scores = np.array([e[2] for e in exploitables])
    print()
    print("  distance mesuree | positifs : mediane %.2f | negatifs : mediane %.2f"
          % (np.median([e[2] for e in pos]), np.median([e[2] for e in neg])))

    print()
    print("=" * 78)
    print("BALAYAGE DU SEUIL DE DECISION")
    print("=" * 78)
    print("  %-7s %6s %6s %6s %6s   %-12s %-12s %-12s"
          % ("seuil", "VP", "FP", "VN", "FN", "sensibilite", "specificite", "exact.equil."))
    grille = np.linspace(max(0.05, float(scores.min())), float(scores.max()), 25)
    resultats = []
    for s in grille:
        tp, fp, tn, fn = matrice(exploitables, s)
        sens, spec, ba, prec, f1 = metriques(tp, fp, tn, fn)
        resultats.append((float(s), tp, fp, tn, fn, sens, spec, ba, prec, f1))
        print("  %-7.2f %6d %6d %6d %6d   %-12.1f %-12.1f %-12.1f"
              % (s, tp, fp, tn, fn, 100 * sens, 100 * spec, 100 * ba))

    s, tp, fp, tn, fn, sens, spec, ba, prec, f1 = max(resultats, key=lambda r: r[7])

    print()
    print("=" * 78)
    print("MEILLEUR POINT DE FONCTIONNEMENT")
    print("=" * 78)
    print("  SEUIL_DISSONANCE_DISTANCE = %.2f" % s)
    print()
    print("                    predit dissonant   predit congruent")
    print("    reel dissonant       %6d             %6d" % (tp, fn))
    print("    reel congruent       %6d             %6d" % (fp, tn))
    print()
    print("  sensibilite (rappel)   : %.1f %%" % (100 * sens))
    print("  specificite            : %.1f %%" % (100 * spec))
    print("  precision              : %.1f %%" % (100 * prec))
    print("  F1                     : %.1f %%" % (100 * f1))
    print("  exactitude equilibree  : %.1f %%" % (100 * ba))

    print()
    print("  Reperes publies sur la tache « expression authentique ou feinte »")
    print("  (ChaLearn LAP, ICCV 2017) :")
    print("     hasard                        %.1f %%" % REPERE_HASARD)
    print("     observateurs humains          %.1f %%" % REPERE_HUMAIN)
    print("     meilleure equipe du challenge %.1f %%" % REPERE_ETAT_ART)
    print()
    print("  -> votre dispositif se situe %+.1f point(s) par rapport a l'observateur humain."
          % (100 * ba - REPERE_HUMAIN))
    print("     A relativiser : tache differente, corpus different, dissonance de")
    print("     synthese. Ce repere situe un ordre de grandeur, il ne compare pas")
    print("     deux mesures equivalentes. A declarer comme tel.")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["clip", "label", "score_distance", "n_fenetres", "emotions"])
            for nom, label, score, n, emo in ech:
                w.writerow([nom, label, "" if score is None else round(score, 4), n, emo])
            w.writerow([])
            w.writerow(["seuil", "VP", "FP", "VN", "FN", "sensibilite", "specificite",
                        "exactitude_equilibree", "precision", "F1"])
            for r in resultats:
                w.writerow([round(r[0], 3)] + list(r[1:5]) + [round(100 * x, 1) for x in r[5:]])
        print()
        print("  Resultats detailles ecrits dans %s" % args.csv)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
