# main.py
import tkinter as tk
from mss import mss
from PIL import Image
import io
import base64
import threading
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# On importe ton propre cerveau !
from back.engine import lancer_cerveau

sct = mss()
image_actuelle_base64 = None

# Cette fonction sera passée au cerveau pour qu'il puisse "voir"
def obtenir_image_courante():
    return image_actuelle_base64

def boucle_capture():
    global image_actuelle_base64
    x, y = fenetre.winfo_rootx(), fenetre.winfo_rooty()
    w, h = fenetre.winfo_width(), fenetre.winfo_height()

    screenshot = sct.grab({"top": y, "left": x, "width": w, "height": h})
    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    img.thumbnail((250, 250))
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    image_actuelle_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    fenetre.after(500, boucle_capture)

def activer_analyse():
    bouton_consentement.destroy()
    label_statut.config(text="📡 ANALYSE CLINIQUE ACTIVE", fg="#00ffcc")
    boucle_capture()
    # On lance l'IA en lui donnant le moyen de récupérer l'image
    threading.Thread(target=lancer_cerveau, args=(obtenir_image_courante,), daemon=True).start()

# --- INTERFACE GRAPHIQUE ---
fenetre = tk.Tk()
fenetre.title("Undr - HUD")
fenetre.geometry("400x200")
fenetre.attributes('-topmost', True)
fenetre.attributes('-alpha', 0.8)
fenetre.configure(bg='#1e1e1e')

label_statut = tk.Label(fenetre, text="⚠️ Consentement requis", font=("Arial", 10, "bold"), fg="#ffcc00", bg="#1e1e1e", pady=20)
label_statut.pack()

bouton_consentement = tk.Button(fenetre, text="Démarrer l'assistance", command=activer_analyse, bg="#00ffcc", fg="#1e1e1e", font=("Arial", 9, "bold"), relief="flat", padx=10)
bouton_consentement.pack(pady=10)

tk.Label(fenetre, text="Posez ce cadre sur le visage du patient", font=("Arial", 8, "italic"), fg="#888888", bg="#1e1e1e").pack(side="bottom", pady=10)

if __name__ == "__main__":
    fenetre.mainloop()