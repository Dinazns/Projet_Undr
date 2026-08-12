"""
Pourquoi le dispositif ne détecte-t-il rien en séance ?

Le banc hors ligne lit un fichier vidéo. Le dispositif, lui, lit DEUX flux que
le banc ne touche jamais : les pixels de l'écran, et le son du haut-parleur
capté en loopback. Quand le premier trouve une dissonance et que le second n'en
trouve aucune, la cause est presque toujours dans ces deux entrées, pas dans
les modèles qui sont pourtant les mêmes.

Cet outil les teste séparément, puis les teste ensemble.

    python -m tools.diagnose --zone 100,100,800,600     # le chemin visuel
    python -m tools.diagnose --audio                    # le chemin sonore
    python -m tools.diagnose --zone 100,100,800,600 --seance 60

La dernière forme ouvre une VRAIE séance sans Electron : elle capture l'écran
et le son comme la boucle d'analyse, fenêtre par fenêtre, et imprime la même
trace que tools/replay.py. Les deux traces sont alors directement comparables
sur la même vidéo, ce qui isole la cause en une seule lecture.
"""
import argparse
import os
import sys
import time
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from config.settings import (  # noqa: E402
    ANALYSIS_WINDOW_SECONDS,
    AUDIO_DEVICE,
    CAPTURE_MAX_SIZE,
    FACE_MIN_SIZE_PX,
    FACE_SAMPLE_INTERVAL,
    SAMPLERATE,
    SEUIL_DISSONANCE_DISTANCE,
    SEUIL_MIN_VOIX,
)

OK = "[ OK ]"
KO = "[ECHEC]"
WARN = "[ ! ]"


# --- Chemin visuel ---------------------------------------------------------

def diagnostiquer_zone(zone: Tuple[int, int, int, int], sortie: Optional[str]) -> bool:
    """
    Capture la zone indiquée et la soumet à la chaîne faciale réelle.

    Ce que l'on cherche : la zone est-elle la bonne, le visage y est-il trouvé,
    et surtout reste-t-il assez grand APRÈS la réduction à CAPTURE_MAX_SIZE ?
    C'est le piège le plus courant, parce qu'un cadre trop large réduit le
    visage en dessous du minimum exploitable sans qu'aucune erreur ne s'affiche.
    """
    import cv2
    from utils.screen_capture import ScreenCapture
    from services.emotion_service import emotion_service

    print()
    print("=" * 78)
    print("CHEMIN VISUEL : capture de la zone %s" % (zone,))
    print("=" * 78)

    cap = ScreenCapture()
    cap.set_hud_coords(*zone)
    frame = cap.capture_hud_array()

    if frame is None:
        print("%s La capture n'a rien renvoye." % KO)
        print("       Zone hors ecran, session verrouillee, ou largeur/hauteur nulles.")
        return False

    h, w = frame.shape[:2]
    print("%s Capture obtenue : %d x %d pixels apres reduction (plafond %d)."
          % (OK, w, h, CAPTURE_MAX_SIZE))
    reduction = max(zone[2], zone[3]) / float(max(w, h))
    if reduction > 1.01:
        print("       La zone demandee faisait %d x %d : elle a ete divisee par %.1f."
              % (zone[2], zone[3], reduction))

    if sortie:
        cv2.imwrite(sortie, frame)
        print("       Image ecrite dans %s : ouvre-la, c'est EXACTEMENT ce que" % sortie)
        print("       le moteur analyse. Si tu n'y vois pas le visage du patient,")
        print("       le probleme est la et nulle part ailleurs.")

    # Detection, avec la meme marge que analyze_face_frame.
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    import mediapipe as mp
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
    res = emotion_service._mp_face_detection.detect(mp_image)

    if not res.detections:
        print("%s Aucun visage detecte dans cette zone." % KO)
        print("       Le moteur ecartera toutes les fenetres avec la mention « visage ».")
        return False

    d = max(res.detections, key=lambda x: x.bounding_box.width * x.bounding_box.height)
    bb = d.bounding_box
    largeur = int(bb.width * 1.4)     # marge de 20 % de part et d'autre
    hauteur = int(bb.height * 1.4)
    print("%s Visage detecte : %d x %d pixels une fois recadre." % (OK, largeur, hauteur))

    if largeur < FACE_MIN_SIZE_PX or hauteur < FACE_MIN_SIZE_PX:
        print("%s Trop petit : le minimum est %d px. Toutes les fenetres seront ecartees."
              % (KO, FACE_MIN_SIZE_PX))
        print("       Resserre le cadre du HUD autour du visage, ou agrandis la video.")
        return False
    if largeur < 100:
        print("%s Exploitable mais juste. La classification perd en finesse sous 100 px."
              % WARN)

    echantillon = emotion_service.analyze_face_frame(frame)
    if not echantillon:
        print("%s Le visage a ete detecte mais la classification a echoue." % KO)
        return False

    v, a = echantillon["coords"]
    vb, ab = echantillon["coords_raw"]
    print("%s Point facial mesure : valence %+.2f, activation %+.2f" % (OK, v, a))
    print("       (valeurs brutes avant mise a l'echelle : %+.2f / %+.2f)" % (vb, ab))
    if abs(v) >= 0.999 or abs(a) >= 0.999:
        print("%s Coordonnee saturee sur la borne : le gain ecrase la mesure." % WARN)
    return True


# --- Chemin sonore ---------------------------------------------------------

def diagnostiquer_audio(duree: float) -> bool:
    """
    Enregistre le loopback et le soumet au modèle vocal réel.

    Le silence est la panne la plus fréquente et la plus silencieuse, au sens
    propre : le moteur écarte la fenêtre avec la mention « voix » et l'interface
    n'affiche rien de plus. Rien ne distingue alors un dispositif qui n'entend
    rien d'un dispositif qui ne trouve rien.
    """
    import soundcard as sc
    from services.emotion_service import emotion_service

    print()
    print("=" * 78)
    print("CHEMIN SONORE : capture loopback de %.1f s" % duree)
    print("=" * 78)
    print("       Fais jouer la video MAINTENANT, son allume.")

    try:
        device = AUDIO_DEVICE or str(sc.default_speaker().name)
    except Exception as exc:
        print("%s Aucun haut-parleur par defaut : %s" % (KO, exc))
        return False
    print("       Peripherique : %s%s"
          % (device, "" if AUDIO_DEVICE else "  (haut-parleur par defaut)"))

    try:
        mic = sc.get_microphone(id=device, include_loopback=True)
        with mic.recorder(samplerate=SAMPLERATE) as rec:
            data = rec.record(numframes=int(SAMPLERATE * duree))
    except Exception as exc:
        print("%s La capture a echoue : %s" % (KO, exc))
        print("       Choisis un autre peripherique dans les parametres du HUD.")
        return False

    if data is None or data.size == 0:
        print("%s Aucun echantillon capte." % KO)
        return False
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    crete = float(np.max(np.abs(data)))
    rms = float(np.sqrt(np.mean(data ** 2)))
    print("       Niveau crete %.4f | niveau efficace %.4f" % (crete, rms))

    if crete <= 0.0:
        print("%s Silence absolu : ce peripherique ne renvoie rien en loopback." % KO)
        print("       Certains casques Bluetooth et USB sont dans ce cas. Vise la")
        print("       carte interne, par exemple « Realtek Digital Output ».")
        return False

    # Le moteur normalise avant de mesurer l'energie : on refait le meme calcul.
    normalise = data / crete
    energie = float(np.mean(normalise ** 2))
    print("       Energie apres normalisation : %.6f (rejet en dessous de 0.000100)"
          % energie)
    if energie < 0.0001:
        print("%s Trop silencieux : chaque fenetre sera ecartee avec la mention « voix »." % KO)
        return False
    satures = float(np.mean(np.abs(normalise) > 0.99))
    if satures > 0.35:
        print("%s Son sature a %.0f %% : rejete au-dela de 35 %%. Baisse le volume."
              % (KO, 100 * satures))
        return False

    emotion, fiabilite, coords = emotion_service.detect_audio_emotion(data, SAMPLERATE)
    if coords is None:
        print("%s Le modele vocal n'a renvoye aucun point." % KO)
        return False

    print("%s Point vocal mesure : valence %+.2f, activation %+.2f"
          % (OK, coords[0], coords[1]))
    print("       Etiquette approchee : %s | fiabilite %.1f | %d sous-fenetre(s)"
          % (emotion, fiabilite, emotion_service.last_voice_subwindows))
    if fiabilite <= SEUIL_MIN_VOIX:
        print("%s Fiabilite sous le plancher de %d : la fenetre serait ecartee."
              % (KO, SEUIL_MIN_VOIX))
        print("       Les sous-fenetres se contredisent. Son trop court, trop bruite,")
        print("       ou plusieurs voix melangees.")
        return False
    if emotion_service.last_voice_subwindows < 2:
        print("%s Une seule sous-fenetre : la fiabilite par concordance est" % WARN)
        print("       impossible et le moteur retombe sur son mode degrade.")
    return True


# --- Séance complète -------------------------------------------------------

def seance(zone: Tuple[int, int, int, int], duree: float, csv_path: Optional[str]) -> None:
    """
    Vraie séance, sans Electron : écran + loopback + AnalysisSession.

    C'est le pendant exact de tools/replay.py, à ceci près que les deux entrées
    sont celles du direct. Comparer les deux traces sur la même vidéo dit
    immédiatement laquelle des deux entrées dégrade la mesure.
    """
    import soundcard as sc
    from services.analysis_session import AnalysisSession
    from services.emotion_service import emotion_service
    from utils.screen_capture import ScreenCapture

    print()
    print("=" * 100)
    print("SEANCE REELLE : ecran + loopback, pendant %.0f s" % duree)
    print("=" * 100)
    print("  Lance la lecture de la video MAINTENANT.")
    print()

    cap = ScreenCapture()
    cap.set_hud_coords(*zone)
    device = AUDIO_DEVICE or str(sc.default_speaker().name)
    mic = sc.get_microphone(id=device, include_loopback=True)
    session = AnalysisSession(emotion_service)
    n_ech = int(SAMPLERATE * ANALYSIS_WINDOW_SECONDS)

    print("  %-9s %4s %-22s %-22s %8s %-10s %s"
          % ("fenetre", "img", "visage", "voix", "distance", "niveau", "montre"))

    lignes = []
    fin = time.monotonic() + duree
    index = 0
    with mic.recorder(samplerate=SAMPLERATE) as recorder:
        while time.monotonic() < fin:
            debut = time.monotonic()
            # L'enregistrement est bloquant : on echantillonne le visage juste
            # avant et juste apres, faute de pouvoir paralleliser sans asyncio.
            # La fenetre reste la meme, seule la repartition des images change.
            images = []
            prochaine = debut
            while time.monotonic() - debut < 0.4:
                if time.monotonic() >= prochaine:
                    f = cap.capture_hud_array()
                    if f is not None:
                        s = emotion_service.analyze_face_frame(f)
                        if s:
                            images.append(s)
                    prochaine += FACE_SAMPLE_INTERVAL
            audio = recorder.record(numframes=n_ech)
            while len(images) < int(ANALYSIS_WINDOW_SECONDS / FACE_SAMPLE_INTERVAL):
                f = cap.capture_hud_array()
                if f is None:
                    break
                s = emotion_service.analyze_face_frame(f)
                if s:
                    images.append(s)
                else:
                    break

            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            out = session.process_window(images, audio, SAMPLERATE)

            if out.evaluated:
                print("  %-9s %4d %-22s %-22s %8.2f %-10s %s"
                      % ("#%d" % index, out.n_face_samples,
                         "%s (%.0f)" % (out.face_emotion, out.face_score),
                         "%s (%.0f)" % (out.voice_emotion, out.voice_score),
                         out.emotion_distance, out.alert_level,
                         "VIBRE" if out.should_vibrate else ""))
            else:
                print("  %-9s %4d -- ecartee : %s"
                      % ("#%d" % index, out.n_face_samples, out.skipped))
            lignes.append((index, out))
            index += 1

    ev = [o for _, o in lignes if o.evaluated]
    alertes = [o for o in ev if o.alert_level != "NONE"]
    print()
    print("  %d fenetre(s), %d evaluee(s), %d alerte(s), %d vibration(s)"
          % (len(lignes), len(ev), len(alertes), sum(1 for o in ev if o.should_vibrate)))
    if len(lignes) and not ev:
        motifs = {}
        for _, o in lignes:
            motifs[o.skipped] = motifs.get(o.skipped, 0) + 1
        print("  AUCUNE fenetre exploitable. Motifs : %s"
              % ", ".join("%s=%d" % kv for kv in sorted(motifs.items())))
        print("  « voix »  -> relance avec --audio")
        print("  « visage » -> relance avec --zone et regarde l'image produite")
    elif ev:
        d = [o.emotion_distance for o in ev]
        print("  distance : min %.2f | mediane %.2f | max %.2f  (seuil %.2f)"
              % (min(d), sorted(d)[len(d) // 2], max(d), SEUIL_DISSONANCE_DISTANCE))

    if csv_path and lignes:
        import csv as _csv
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["fenetre", "evaluee", "ecartee", "images_visage", "visage",
                        "fiab_visage", "voix", "fiab_voix", "distance", "niveau",
                        "score", "vibration"])
            for i, o in lignes:
                w.writerow([i, o.evaluated, o.skipped or "", o.n_face_samples,
                            o.face_emotion or "", round(o.face_score, 1),
                            o.voice_emotion or "", round(o.voice_score, 1),
                            round(o.emotion_distance, 3), o.alert_level,
                            round(o.confidence, 1), o.should_vibrate])
        print("  Trace ecrite dans %s" % csv_path)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--zone", default=None,
                   help="zone d'ecran a analyser : x,y,largeur,hauteur")
    p.add_argument("--image", default="capture_diagnostic.png",
                   help="ou ecrire l'image capturee")
    p.add_argument("--audio", action="store_true", help="teste la capture loopback")
    p.add_argument("--duree-audio", type=float, default=3.0)
    p.add_argument("--seance", type=float, default=0,
                   help="duree d'une vraie seance a tracer, en secondes")
    p.add_argument("--csv", default=None)
    args = p.parse_args()

    if not args.zone and not args.audio and not args.seance:
        p.error("indiquez --zone, --audio ou --seance")

    zone = None
    if args.zone:
        try:
            zone = tuple(int(v) for v in args.zone.split(","))
            if len(zone) != 4:
                raise ValueError
        except ValueError:
            p.error("--zone attend quatre entiers : x,y,largeur,hauteur")

    print("Configuration en vigueur : fenetre %.1f s | image toutes les %.2f s | "
          "capture reduite a %d px" % (ANALYSIS_WINDOW_SECONDS, FACE_SAMPLE_INTERVAL,
                                       CAPTURE_MAX_SIZE))

    visuel = sonore = None
    if zone and not args.seance:
        visuel = diagnostiquer_zone(zone, args.image)
    if args.audio:
        sonore = diagnostiquer_audio(args.duree_audio)
    if args.seance:
        if not zone:
            p.error("--seance exige --zone")
        seance(zone, args.seance, args.csv)
        return 0

    print()
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    if visuel is False or sonore is False:
        print("  Une entree au moins est defaillante. Tant qu'elle l'est, le")
        print("  dispositif ne peut RIEN detecter, et ce n'est pas un defaut des")
        print("  modeles : la fenetre est ecartee avant meme la comparaison.")
        return 1
    if visuel and sonore:
        print("  Les deux entrees fonctionnent. Relance avec --seance pour voir")
        print("  ce que la boucle decide fenetre par fenetre, et compare cette")
        print("  trace a celle de tools/replay.py sur la meme video.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
