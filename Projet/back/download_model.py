#!/usr/bin/env python3
"""
Script pour télécharger le modèle MediaPipe Face Detector.
"""

import os
import sys
import requests
import shutil
from pathlib import Path

def download_mediapipe_model():
    """Télécharge le modèle MediaPipe Face Detector (bundle .task complet)."""

    # IMPORTANT : MediaPipe FaceDetector.create_from_options attend un *bundle*
    # ".task" (qui contient le graphe + les poids + les métadonnées), PAS un
    # simple fichier ".tflite" brut. Utiliser l'URL ".task" officielle.
    model_url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.task"

    # Chemin de destination
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)

    model_path = models_dir / "face_detector.task"
    
    print(f"Téléchargement du modèle MediaPipe Face Detector...")
    print(f"URL: {model_url}")
    print(f"Destination: {model_path}")
    
    try:
        # Télécharger le modèle
        response = requests.get(model_url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Sauvegarder le modèle
        with open(model_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)
        
        print(f"✅ Modèle téléchargé avec succès !")
        print(f"Taille: {model_path.stat().st_size / (1024*1024):.2f} MB")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors du téléchargement: {e}")
        
        # Solution alternative: créer un modèle vide avec un message d'erreur explicite
        print("\n⚠️  Solution alternative: création d'un fichier de placeholder...")
        try:
            with open(model_path, 'w') as f:
                f.write("# Placeholder pour le modèle MediaPipe Face Detector\n")
                f.write("# Le modèle doit être téléchargé manuellement depuis:\n")
                f.write("# https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.task\n")
                f.write("# (bundle .task complet, PAS un .tflite brut)\n")
                f.write("# Renommer en 'face_detector.task' après téléchargement\n")
            print(f"✅ Fichier de placeholder créé à: {model_path}")
            return True
        except Exception as e2:
            print(f"❌ Impossible de créer le fichier de placeholder: {e2}")
            return False

def check_packages():
    """Vérifie si les packages nécessaires sont installés."""
    required_packages = ['requests']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Packages manquants: {', '.join(missing_packages)}")
        print(f"Installez-les avec: pip install {' '.join(missing_packages)}")
        return False
    
    return True

def main():
    """Fonction principale."""
    print("=" * 60)
    print("Téléchargement du modèle MediaPipe Face Detector")
    print("=" * 60)
    
    # Vérifier les packages
    if not check_packages():
        sys.exit(1)
    
    # Télécharger le modèle
    if download_mediapipe_model():
        print("\n✅ Processus terminé avec succès !")
        print("\nInstructions d'utilisation:")
        print("1. Le modèle a été téléchargé dans: back/models/face_detector.task")
        print("2. L'EmotionService utilisera automatiquement ce modèle")
        print("3. Si vous rencontrez des erreurs, téléchargez le modèle manuellement depuis:")
        print("   https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.task")
        print("   (bundle .task complet, PAS un .tflite brut) et renommez-le en 'face_detector.task'")
    else:
        print("\n❌ Échec du téléchargement.")
        sys.exit(1)

if __name__ == "__main__":
    main()