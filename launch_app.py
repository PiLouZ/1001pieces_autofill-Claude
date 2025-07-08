#!/usr/bin/env python3
"""
Lanceur principal pour l'application 1001pieces_autofill
Ce script lance l'application sans terminal visible
"""

import sys
import os
import subprocess

def main():
    """Lancer l'application sans terminal"""
    # Chemin vers le script principal
    app_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(app_dir, 'src', 'ui', 'main_refactored.py')
    
    # Utiliser pythonw pour éviter le terminal (sur macOS/Windows)
    if sys.platform == 'darwin':  # macOS
        # Utiliser pythonw si disponible, sinon python avec nohup
        try:
            subprocess.Popen(['/usr/bin/env', 'pythonw', '-m', 'src.ui.main_refactored'], 
                           cwd=app_dir,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            # Fallback si pythonw n'est pas disponible
            subprocess.Popen(['/usr/bin/env', 'python3', '-m', 'src.ui.main_refactored'], 
                           cwd=app_dir,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    else:
        # Windows/Linux
        try:
            subprocess.Popen([sys.executable.replace('python', 'pythonw'), '-m', 'src.ui.main_refactored'], 
                           cwd=app_dir,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except:
            subprocess.Popen([sys.executable, '-m', 'src.ui.main_refactored'], 
                           cwd=app_dir,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    main()