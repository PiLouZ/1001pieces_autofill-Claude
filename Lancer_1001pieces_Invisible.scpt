#!/usr/bin/env osascript

# Script AppleScript pour lancer l'application sans terminal
# Ce script est complètement invisible pour l'utilisateur

on run
    try
        # Obtenir le répertoire du script
        set scriptPath to (path to me) as string
        set projectPath to do shell script "dirname " & quoted form of POSIX path of scriptPath
        
        # Changer vers le répertoire du projet et lancer l'application
        do shell script "cd " & quoted form of projectPath & " && python3 run.py > /dev/null 2>&1 &"
        
    on error errorMessage
        display alert "Erreur de lancement" message errorMessage
    end try
end run