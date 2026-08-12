"""
Montage d'une vidéo de démonstration à partir d'un corpus étiqueté.

Produit un seul fichier lisible en boucle pendant la soutenance, enchaînant des
extraits congruents et des extraits dissonants, séparés par un silence noir.

POURQUOI LE SILENCE ENTRE LES EXTRAITS
--------------------------------------
Les extraits durent 2 à 4 secondes, la fenêtre d'analyse 3 s. Collés bout à
bout, une fenêtre chevaucherait deux extraits différents, le visage d'un
locuteur et la voix d'un autre, et produirait une fausse dissonance à chaque
transition.

L'insertion d'un silence noir d'au moins une fenêtre déclenche la purge de
contexte du moteur : la mémoire des deux canaux est vidée entre deux extraits.
C'est le mécanisme prévu pour les ruptures de scène, et la démonstration
l'exerce donc en direct.

CE QUE CE MONTAGE EST, ET N'EST PAS
-----------------------------------
En mode `illustratif` (défaut), les extraits sont choisis parmi ceux que le
système classe le mieux. **C'est une illustration, pas une mesure.** La mesure,
c'est le résultat du banc sur l'ensemble du corpus. Les deux ne se confondent
pas et doivent être présentés séparément :

    « Voici des exemples illustratifs du fonctionnement en direct. La
      performance mesurée sur l'ensemble du corpus étiqueté figure dans le
      rapport de benchmark, elle ne se lit pas sur ces extraits. »

Le mode `aleatoire` tire au hasard : plus honnête à montrer, plus risqué en
direct. À vous de voir ce que vous assumez.

    python -m tools.make_demo_reel --resultats resultats.csv \
        --media ..\\..\\crema-d --sortie demo.mp4
"""
import argparse
import csv
import os
import random
import shutil
import subprocess
import sys
import tempfile

# Normalisation commune à tous les segments : sans elle, la concaténation
# échoue dès que deux extraits diffèrent en résolution ou en fréquence.
LARGEUR, HAUTEUR, FPS, SR = 480, 360, 30, 44100


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit("ffmpeg introuvable. Installez-le, ou : pip install imageio-ffmpeg")


def lire_resultats(path):
    """Renvoie [(clip, label, distance)] pour les clips exploitables."""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            if not r or r[0] == "seuil":
                break
            if r[0] == "clip" or len(r) < 4 or r[2] == "":
                continue
            out.append((r[0], int(r[1]), float(r[2])))
    return out


def trouver_media(nom, racine):
    for sous, ext in (("VideoFlash", ".flv"), ("", ".flv"), ("", ".mp4")):
        p = os.path.join(racine, sous, nom + ext) if sous else os.path.join(racine, nom + ext)
        if os.path.exists(p):
            return p
    return None


def normaliser(ff, source, dest, legende=None):
    filtres = ("scale=%d:%d:force_original_aspect_ratio=decrease,"
               "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,fps=%d,format=yuv420p"
               % (LARGEUR, HAUTEUR, LARGEUR, HAUTEUR, FPS))
    if legende:
        texte = legende.replace(":", "\\:").replace("'", "")
        filtres += (",drawtext=text='%s':x=12:y=h-28:fontsize=16:fontcolor=white:"
                    "box=1:boxcolor=black@0.5:boxborderw=6" % texte)
    cmd = [ff, "-v", "error", "-y", "-i", source,
           "-vf", filtres, "-r", str(FPS),
           "-ar", str(SR), "-ac", "1",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "aac", "-b:a", "128k", dest]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def separateur(ff, dest, duree):
    cmd = [ff, "-v", "error", "-y",
           "-f", "lavfi", "-i", "color=c=black:s=%dx%d:r=%d:d=%.2f" % (LARGEUR, HAUTEUR, FPS, duree),
           "-f", "lavfi", "-i", "anullsrc=r=%d:cl=mono" % SR,
           "-t", "%.2f" % duree,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", dest]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resultats", required=True, help="CSV produit par tools.benchmark")
    p.add_argument("--media", required=True, help="racine des fichiers vidéo")
    p.add_argument("--sortie", default="demo.mp4")
    p.add_argument("--n", type=int, default=6, help="extraits par classe")
    p.add_argument("--mode", choices=("illustratif", "aleatoire"), default="illustratif")
    p.add_argument("--silence", type=float, default=3.5,
                   help="durée du séparateur noir. Doit dépasser une fenêtre "
                        "d'analyse, sans quoi la purge de contexte ne se "
                        "déclenche pas entre deux extraits")
    p.add_argument("--annoter", action="store_true",
                   help="incruste l'étiquette réelle dans l'image (à éviter en soutenance)")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    ff = ffmpeg_exe()
    rows = lire_resultats(args.resultats)
    if not rows:
        print("Aucun clip exploitable dans %s" % args.resultats)
        return 1

    pos = [r for r in rows if r[1] == 1]
    neg = [r for r in rows if r[1] == 0]
    if args.mode == "illustratif":
        pos.sort(key=lambda x: -x[2])
        neg.sort(key=lambda x: x[2])
    else:
        rnd = random.Random(args.seed)
        rnd.shuffle(pos)
        rnd.shuffle(neg)
    pos, neg = pos[:args.n], neg[:args.n]

    # Congruents d'abord : la jauge doit rester basse, ce qui établit la
    # référence avant de montrer les dissonances.
    sequence = [(c, "congruent", d) for c, _, d in neg] + [(c, "dissonant", d) for c, _, d in pos]

    print("Mode      : %s" % args.mode)
    if args.mode == "illustratif":
        print("            /!\\ extraits choisis parmi les mieux classés :")
        print("            c'est une ILLUSTRATION, pas une mesure. Annoncez le")
        print("            chiffre global du banc séparément.")
    print("Séquence  : %d congruents puis %d dissonants" % (len(neg), len(pos)))
    print("Séparateur: %.1f s de noir silencieux (purge du contexte entre extraits)" % args.silence)
    print()

    tmp = tempfile.mkdtemp(prefix="undr_demo_")
    segments, absents = [], 0
    try:
        sep = os.path.join(tmp, "sep.mp4")
        if not separateur(ff, sep, args.silence):
            print("Impossible de générer le séparateur.")
            return 1

        for i, (nom, classe, dist) in enumerate(sequence):
            src = trouver_media(nom, args.media)
            if not src:
                absents += 1
                continue
            dest = os.path.join(tmp, "seg%03d.mp4" % i)
            legende = ("%s  (distance mesuree %.2f)" % (classe, dist)) if args.annoter else None
            if normaliser(ff, src, dest, legende):
                segments.append(dest)
                print("  %-24s %-10s distance %.2f" % (nom, classe, dist), flush=True)
            else:
                absents += 1

        if not segments:
            print("Aucun segment produit.")
            return 1

        liste = os.path.join(tmp, "liste.txt")
        with open(liste, "w", encoding="utf-8") as f:
            f.write("file '%s'\n" % sep.replace("\\", "/"))
            for s in segments:
                f.write("file '%s'\n" % s.replace("\\", "/"))
                f.write("file '%s'\n" % sep.replace("\\", "/"))

        r = subprocess.run([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0",
                            "-i", liste, "-c", "copy", args.sortie],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("Concaténation échouée : %s" % r.stderr.strip()[:300])
            return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    taille = os.path.getsize(args.sortie) / 1e6
    print()
    print("  %d segment(s) montés, %d ignoré(s)" % (len(segments), absents))
    print("  -> %s (%.1f Mo)" % (os.path.abspath(args.sortie), taille))
    print()
    print("  Lisez-la en plein écran, placez le cadre du HUD sur le visage,")
    print("  et laissez tourner en boucle. La jauge doit rester basse sur la")
    print("  première moitié, puis monter sur la seconde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
