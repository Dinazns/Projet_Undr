"""
Récupération sélective des vidéos de CREMA-D.

Le dépôt pèse 7,5 Go parce qu'il contient les 7 442 clips en trois formats
(VideoFlash, AudioMP3, AudioWAV). Une évaluation n'a besoin que des clips
étiquetés, une centaine. Ce script construit la liste exacte et ne récupère
que ceux-là.

DEUX PIÈGES CONNUS
------------------
1. Le miroir Kaggle de CREMA-D ne publie que le dossier `AudioWAV`. Aucune
   vidéo dedans.

2. Le dépôt GitHub a **épuisé son budget LFS**. Un `git clone` classique
   ramène bien les CSV et les scripts, puis échoue sur les médias avec :

       batch response: This repository exceeded its LFS budget.

   Ce n'est pas une erreur de votre côté. Les auteurs maintiennent pour cette
   raison un miroir GitLab, qui sert les médias :

       https://gitlab.com/cs-cooper-lab/crema-d-mirror

MODE D'EMPLOI
-------------
    # 1. clone léger du miroir : les médias ne sont pas téléchargés
    set GIT_LFS_SKIP_SMUDGE=1
    git clone https://gitlab.com/cs-cooper-lab/crema-d-mirror.git crema-d

    # 2. récupération des seuls clips étiquetés
    python -m tools.crema_fetch --labels crema_labels.csv --repo crema-d

    # 3. mesure
    python -m tools.benchmark --labels crema_labels.csv --media crema-d --degrade
"""
import argparse
import csv
import os
import subprocess
import sys

MIROIR = "https://gitlab.com/cs-cooper-lab/crema-d-mirror.git"

# Clips signalés défectueux par les auteurs (audio absent, durée nulle, ou
# contenu ne correspondant pas au nom de fichier).
DEFECTUEUX = {
    "1076_MTI_NEU_XX", "1076_MTI_SAD_XX", "1064_TIE_SAD_XX", "1064_IEO_DIS_MD",
}

# git lfs pull accepte une liste séparée par des virgules, mais la ligne de
# commande Windows plafonne : on découpe.
TAILLE_LOT = 40


def noms_depuis_labels(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r["clip"].strip() for r in csv.DictReader(f)
                if r.get("clip") and r["clip"].strip() not in DEFECTUEUX]


def taille_dossier(chemin):
    total = 0
    for racine, _, fichiers in os.walk(chemin):
        for f in fichiers:
            try:
                total += os.path.getsize(os.path.join(racine, f))
            except OSError:
                pass
    return total


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--labels", required=True,
                   help="CSV clip,label produit par crema_incongruence")
    p.add_argument("--repo", required=True,
                   help="dossier du clone du miroir GitLab")
    p.add_argument("--audio", action="store_true",
                   help="récupère aussi AudioWAV (inutile si vous avez déjà le miroir Kaggle)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="affiche les commandes sans les exécuter")
    args = p.parse_args()

    if not os.path.isdir(os.path.join(args.repo, ".git")):
        print("Le dossier %s n'est pas un clone git." % args.repo)
        print()
        print("Clonez d'abord le miroir GitLab, sans télécharger les médias :")
        print()
        print("    set GIT_LFS_SKIP_SMUDGE=1")
        print("    git clone %s %s" % (MIROIR, args.repo))
        print()
        print("(PowerShell : $env:GIT_LFS_SKIP_SMUDGE=\"1\")")
        return 1

    noms = noms_depuis_labels(args.labels)
    if args.limit:
        noms = noms[:args.limit]
    if not noms:
        print("Aucun clip dans %s" % args.labels)
        return 1

    dossiers = ["VideoFlash"] + (["AudioWAV"] if args.audio else [])
    motifs = ["%s/%s%s" % (d, n, ".flv" if d == "VideoFlash" else ".wav")
              for n in noms for d in dossiers]

    print("Dépôt   : %s" % os.path.abspath(args.repo))
    print("Clips   : %d" % len(noms))
    print("Fichiers: %d (%s)" % (len(motifs), ", ".join(dossiers)))
    print("Lots    : %d" % ((len(motifs) + TAILLE_LOT - 1) // TAILLE_LOT))
    print()

    avant = taille_dossier(args.repo)
    echecs = 0
    for i in range(0, len(motifs), TAILLE_LOT):
        lot = motifs[i:i + TAILLE_LOT]
        cmd = ["git", "lfs", "pull", "--include=" + ",".join(lot)]
        num = i // TAILLE_LOT + 1
        print("  lot %d : %d fichier(s)" % (num, len(lot)), flush=True)
        if args.dry_run:
            print("     %s" % " ".join(cmd[:3] + ["--include=<%d fichiers>" % len(lot)]))
            continue
        r = subprocess.run(cmd, cwd=args.repo, capture_output=True, text=True)
        if r.returncode != 0:
            echecs += 1
            print("     ECHEC : %s" % (r.stderr.strip().splitlines()[-1:] or ["?"])[0])

    if args.dry_run:
        return 0

    gagne = taille_dossier(args.repo) - avant
    print()
    print("  %.0f Mo récupérés, %d lot(s) en échec" % (gagne / 1e6, echecs))

    presents = 0
    for n in noms:
        f = os.path.join(args.repo, "VideoFlash", n + ".flv")
        if os.path.exists(f) and os.path.getsize(f) > 10000:
            presents += 1
    print("  %d/%d vidéo(s) réellement présentes (taille > 10 Ko)" % (presents, len(noms)))

    if presents == 0:
        print()
        print("  Aucun média récupéré. Vérifiez que le dépôt pointe bien sur le miroir :")
        print("     git -C %s remote -v" % args.repo)
        print("  S'il pointe sur github.com, le budget LFS y est épuisé : reclonez GitLab.")
        return 1

    print()
    print("  Suite :")
    print("     python -m tools.benchmark --labels %s --media %s --degrade"
          % (args.labels, args.repo))
    print()
    print("  Si OpenCV n'ouvre pas les .flv :")
    print("     ffmpeg -i VideoFlash/NOM.flv -c:v libx264 -c:a aac VideoFlash/NOM.mp4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
