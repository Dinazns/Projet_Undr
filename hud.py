import tkinter as tk

def valider_consentement():
    # Change l'état de l'interface quand on clique
    bouton_consentement.destroy() # On enlève le bouton
    label_statut.config(text="🔍 Analyse en cours...", fg="#ff3366") # Rouge/Rose pour l'alerte
    # Ici, on lancera plus tard la fonction de capture d'écran
    print("Consentement validé. Prêt pour la Phase 2.")

# 1. Fenêtre principale
fenetre = tk.Tk()
fenetre.title("Undr - Assistant")
fenetre.geometry("400x200")
fenetre.attributes('-topmost', True)
fenetre.attributes('-alpha', 0.85)
fenetre.configure(bg='#1e1e1e')

# 2. Titre / Statut
label_statut = tk.Label(
    fenetre, 
    text="⚠️ En attente du consentement patient", 
    font=("Arial", 10, "bold"), 
    fg="#ffcc00", # Jaune pour l'attente
    bg="#1e1e1e",
    pady=20
)
label_statut.pack()

# 3. Bouton de validation (Le "Consentement")
bouton_consentement = tk.Button(
    fenetre, 
    text="Le patient est informé et consent", 
    command=valider_consentement,
    bg="#00ffcc", 
    fg="#1e1e1e",
    font=("Arial", 9, "bold"),
    padx=10,
    pady=5,
    relief="flat"
)
bouton_consentement.pack(pady=10)

# 4. Message d'aide
tk.Label(
    fenetre, 
    text="Positionnez cette fenêtre sur le visage du patient", 
    font=("Arial", 8, "italic"), 
    fg="#888888", 
    bg="#1e1e1e"
).pack(side="bottom", pady=10)

fenetre.mainloop()