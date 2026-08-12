"""
Rejoue une vidéo dans la boucle d'analyse réelle, fenêtre par fenêtre.

C'est le banc le plus fidèle du dépôt : il ne mesure pas un corpus, il rejoue
une séance. Chaque fenêtre est traitée comme api.main la traite en direct, dans
le même ordre, avec les mêmes réglages, et la trace produite est celle que le
praticien aurait vue défiler dans le widget.

Ce qui est REPRODUIT à l'identique
----------------------------------
  - fenêtres de ANALYSIS_WINDOW_SECONDS qui se suivent sans recouvrement, à
    partir du début du flux ;
  - aucun recalage sur la parole : le dispositif ne sait pas où elle se trouve ;
  - visage échantillonné toutes les FACE_SAMPLE_INTERVAL secondes PENDANT la
    fenêtre audio, jamais après ;
  - image réduite à CAPTURE_MAX_SIZE, comme le fait capture_hud_array() ;
  - une seule AnalysisSession pour tout le rejeu, avec sa mémoire, ses purges,
    sa persistance et son délai réfractaire ;
  - décision prise fenêtre par fenêtre, sans jamais choisir a posteriori la
    meilleure d'entre elles.

Ce qui reste INÉVITABLEMENT différent
-------------------------------------
  - la source est un fichier et non la capture d'un écran, donc l'image ne
    subit ni le rendu de la visioconférence ni celui du bureau ;
  - le son vient du fichier et non du loopback ;
  - le temps n'est pas réel : les fenêtres s'enchaînent aussi vite que le
    processeur le permet. Cela ne change aucune décision, la logique ne
    consultant l'horloge que pour le délai réfractaire, qui est donc simulé.

    python -m tools.replay --video ../../Video/generated_video.mp4
    python -m tools.replay --video ... --csv seance.csv
"""
import argparse
import csv
import logging
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from config.settings import (  # noqa: E402
    ALERT_MODERATE_CONFIDENCE,
    ALERT_MODERATE_DISTANCE,
    ALERT_SEVERE_CONFIDENCE,
    ALERT_SEVERE_DISTANCE,
    ANALYSIS_WINDOW_SECONDS,
    CAPTURE_MAX_SIZE,
    FACE_SAMPLE_INTERVAL,
    PERSISTENCE_MIN,
    SAMPLERATE,
    SEUIL_DISSONANCE_DISTANCE,
    VIBRATION_COOLDOWN_SECONDS,
    VOICE_SUBWINDOW_MIN_SECONDS,
)
from services.analysis_session import AnalysisSession  # noqa: E402
from services.emotion_service import emotion_service  # noqa: E402
from tools.evaluate_corpus import analyse_frames, load_audio  # noqa: E402


class HorlogeSimulee:
    """
    Horloge avançant d'une fenêtre à chaque appel.

    Le délai réfractaire entre deux vibrations se compte en secondes de séance,
    pas en secondes de calcul. Rejouer une vidéo plus vite que le temps réel
    avec l'horloge du système ferait passer toutes les fenêtres dans le même
    intervalle réfractaire et supprimerait des vibrations que le praticien
    aurait bel et bien reçues.
    """

    def __init__(self, pas: float):
        self._pas = pas
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def avancer(self) -> None:
        self._t += self._pas


def rejouer(video: str, audio_path: Optional[str] = None,
            verbose: bool = False) -> List[dict]:
    """Rejoue un fichier et renvoie une ligne par fenêtre."""
    frames = analyse_frames(video, degrade=False)
    audio = load_audio(audio_path or video)
    duree = len(audio) / float(SAMPLERATE)

    horloge = HorlogeSimulee(ANALYSIS_WINDOW_SECONDS)
    # Session unique pour tout le rejeu : c'est une séance, pas une collection
    # de clips indépendants. La mémoire, les purges et le délai réfractaire
    # traversent donc les fenêtres, exactement comme en direct.
    session = AnalysisSession(emotion_service, clock=horloge)

    n_ech = int(ANALYSIS_WINDOW_SECONDS * SAMPLERATE)
    lignes = []
    debut = 0.0
    index = 0

    while debut + ANALYSIS_WINDOW_SECONDS <= duree + 1e-6:
        a0 = int(debut * SAMPLERATE)
        bloc = audio[a0:a0 + n_ech]
        echantillons = [s for (ts, s) in frames
                        if debut <= ts < debut + ANALYSIS_WINDOW_SECONDS]

        out = session.process_window(echantillons, bloc, SAMPLERATE)
        horloge.avancer()

        lignes.append({
            "fenetre": index,
            "debut_s": round(debut, 2),
            "fin_s": round(debut + ANALYSIS_WINDOW_SECONDS, 2),
            "evaluee": out.evaluated,
            "ecartee": out.skipped or "",
            "images_visage": out.n_face_samples,
            "dispersion": (round(out.face_dispersion, 3)
                           if out.face_dispersion is not None else ""),
            "visage": out.face_emotion or "",
            "fiab_visage": round(out.face_score, 1),
            "visage_valence": (round(out.face_coords[0], 3) if out.face_coords else ""),
            "visage_arousal": (round(out.face_coords[1], 3) if out.face_coords else ""),
            "voix": out.voice_emotion or "",
            "fiab_voix": round(out.voice_score, 1),
            "voix_valence": (round(out.voice_coords[0], 3) if out.voice_coords else ""),
            "voix_arousal": (round(out.voice_coords[1], 3) if out.voice_coords else ""),
            "sous_fenetres_voix": out.voice_subwindows,
            "distance": round(out.emotion_distance, 3),
            "niveau": out.alert_level,
            "score": round(out.confidence, 1),
            "vibration": out.should_vibrate,
        })
        debut += ANALYSIS_WINDOW_SECONDS
        index += 1

    return lignes


def tracer(lignes: List[dict], nom: str) -> None:
    """Affiche le déroulé de la séance, une ligne par fenêtre."""
    print()
    print("=" * 100)
    print("DEROULE DE LA SEANCE : %s" % nom)
    print("=" * 100)
    print("  %-13s %4s %-22s %-22s %8s %-10s %s"
          % ("fenetre", "img", "visage", "voix", "distance", "niveau", "montre"))
    for r in lignes:
        if not r["evaluee"]:
            print("  %-13s %4d %-22s %-22s %8s %-10s"
                  % ("%5.1f-%5.1f" % (r["debut_s"], r["fin_s"]), r["images_visage"],
                     "-- ecartee : %s" % r["ecartee"], "", "", ""))
            continue
        visage = "%s (%.0f)" % (r["visage"], r["fiab_visage"])
        voix = "%s (%.0f)" % (r["voix"], r["fiab_voix"])
        print("  %-13s %4d %-22s %-22s %8.2f %-10s %s"
              % ("%5.1f-%5.1f" % (r["debut_s"], r["fin_s"]), r["images_visage"],
                 visage, voix, r["distance"], r["niveau"],
                 "VIBRE" if r["vibration"] else ""))


def resumer(lignes: List[dict]) -> None:
    ev = [r for r in lignes if r["evaluee"]]
    alertes = [r for r in ev if r["niveau"] != "NONE"]
    vibrations = [r for r in ev if r["vibration"]]

    print()
    print("-" * 100)
    print("  fenetres produites : %d | evaluees : %d (%.0f %%)"
          % (len(lignes), len(ev), 100 * len(ev) / max(len(lignes), 1)))
    if len(ev) < len(lignes):
        motifs = {}
        for r in lignes:
            if not r["evaluee"]:
                motifs[r["ecartee"]] = motifs.get(r["ecartee"], 0) + 1
        print("  ecartees : %s" % ", ".join("%s=%d" % kv for kv in sorted(motifs.items())))

    niveaux = {}
    for r in alertes:
        niveaux[r["niveau"]] = niveaux.get(r["niveau"], 0) + 1
    print("  alertes : %d / %d fenetres evaluees%s"
          % (len(alertes), len(ev),
             (" (%s)" % ", ".join("%s=%d" % kv for kv in sorted(niveaux.items())))
             if niveaux else ""))
    print("  VIBRATIONS ENVOYEES A LA MONTRE : %d" % len(vibrations))
    if vibrations:
        print("     aux instants : %s"
              % ", ".join("%.1f s" % r["debut_s"] for r in vibrations))

    if ev:
        d = np.array([r["distance"] for r in ev], dtype=float)
        print("  distance visage/voix : min %.2f | mediane %.2f | max %.2f  (seuil %.2f)"
              % (d.min(), float(np.median(d)), d.max(), SEUIL_DISSONANCE_DISTANCE))

    mono = [r for r in ev if r["sous_fenetres_voix"] < 2]
    if mono:
        print("  ATTENTION : %d fenetre(s) n'ont produit qu'une sous-fenetre vocale ;"
              % len(mono))
        print("  la fiabilite par concordance y est impossible.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True, nargs="+",
                   help="un ou plusieurs fichiers video a rejouer")
    p.add_argument("--audio", default=None,
                   help="bande son a substituer (un seul fichier video attendu)")
    p.add_argument("--csv", default=None, help="sortie CSV, une ligne par fenetre")
    p.add_argument("--verbose", action="store_true",
                   help="affiche aussi les journaux internes du moteur")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="    %(levelname)s %(name)s : %(message)s", stream=sys.stdout,
    )

    print("CONDITIONS DE REJEU : celles de la boucle d'analyse reelle.")
    print("  fenetre %.1f s, sans recouvrement, depuis le debut du flux"
          % ANALYSIS_WINDOW_SECONDS)
    print("  image toutes les %.2f s pendant la fenetre | capture reduite a %d px"
          % (FACE_SAMPLE_INTERVAL, CAPTURE_MAX_SIZE))
    print("  sous-fenetre vocale minimale %.1f s | seuils %.2f / %.2f / %.2f"
          % (VOICE_SUBWINDOW_MIN_SECONDS, SEUIL_DISSONANCE_DISTANCE,
             ALERT_MODERATE_DISTANCE, ALERT_SEVERE_DISTANCE))
    print("  ou confiance %.0f / %.0f | persistance %d | delai refractaire %.0f s"
          % (ALERT_MODERATE_CONFIDENCE, ALERT_SEVERE_CONFIDENCE,
             PERSISTENCE_MIN, VIBRATION_COOLDOWN_SECONDS))
    print("  aucune degradation ajoutee, aucun recalage sur la parole")

    toutes = []
    for chemin in args.video:
        if not os.path.exists(chemin):
            print("Introuvable : %s" % chemin)
            continue
        lignes = rejouer(chemin, args.audio if len(args.video) == 1 else None,
                         args.verbose)
        if not lignes:
            print()
            print("  %s : aucune fenetre complete de %.1f s n'entre dans ce fichier."
                  % (os.path.basename(chemin), ANALYSIS_WINDOW_SECONDS))
            continue
        tracer(lignes, os.path.basename(chemin))
        resumer(lignes)
        for r in lignes:
            r["fichier"] = os.path.basename(chemin)
        toutes.extend(lignes)

    if args.csv and toutes:
        cols = ["fichier", "fenetre", "debut_s", "fin_s", "evaluee", "ecartee",
                "images_visage", "dispersion", "visage", "fiab_visage",
                "visage_valence", "visage_arousal", "voix", "fiab_voix",
                "voix_valence", "voix_arousal", "sous_fenetres_voix",
                "distance", "niveau", "score", "vibration"]
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(toutes)
        print()
        print("  %d ligne(s) ecrites dans %s" % (len(toutes), args.csv))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
