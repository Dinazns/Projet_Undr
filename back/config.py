# config.py
import os
from dotenv import load_dotenv

# Chargement de la clé API
load_dotenv()
HUME_API_KEY = os.getenv("HUME_API_KEY")

# Modèle de Russell
TOUS_LES_GROUPES = {
    "Q1 (Actif/Positif)": [
        "Amusement", "Awe", "Desire", "Determination", "Ecstasy", 
        "Enthusiasm", "Excitement", "Joy", "Pride", "Romance", 
        "Surprise (positive)", "Triumph"
    ],
    "Q2 (Calme/Positif)": [
        "Admiration", "Adoration", "Aesthetic Appreciation", "Calmness", 
        "Concentration", "Contemplation", "Contentment", "Entrancement", 
        "Interest", "Love", "Nostalgia", "Relief", "Satisfaction"
    ],
    "Q3 (Passif/Négatif)": [
        "Awkwardness", "Boredom", "Confusion", "Disappointment", "Doubt", 
        "Embarrassment", "Empathic Pain", "Neutral", "Sadness", 
        "Sympathy", "Tiredness"
    ],
    "Q4 (Actif/Négatif)": [
        "Anger", "Anxiety", "Contempt", "Craving", "Disgust", "Distress", 
        "Envy", "Fear", "Guilt", "Horror", "Pain", "Shame", "Surprise (negative)"
    ]
}