#!/usr/bin/env pythonw
"""
Lanceur invisible pour l'application 1001pieces_autofill
Ce script utilise pythonw pour éviter complètement l'affichage du terminal
"""

import sys
import os
import subprocess

def main():
    """Lancer l'application de manière invisible"""
    # Obtenir le répertoire de ce script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Chemin vers run.py
    run_script = os.path.join(script_dir, 'run.py')
    
    try:
        # Vérifier que run.py existe
        if not os.path.exists(run_script):
            import tkinter.messagebox as msgbox
            msgbox.showerror("Erreur", "Le fichier run.py est introuvable")
            return
        
        # Lancer l'application avec python (pas pythonw car run.py gère l'affichage)
        # mais détacher complètement du processus parent
        if sys.platform == 'darwin':  # macOS
            subprocess.Popen([
                '/usr/bin/env', 'python3', run_script
            ], 
            cwd=script_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True)
        else:
            subprocess.Popen([
                sys.executable, run_script
            ], 
            cwd=script_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, 'DETACHED_PROCESS') else 0)
            
    except Exception as e:
        try:
            import tkinter.messagebox as msgbox
            msgbox.showerror("Erreur de lancement", str(e))
        except:
            print(f"Erreur: {e}")

if __name__ == "__main__":
    main()