#!/usr/bin/env python3
"""
Script pour nettoyer automatiquement les print statements excessifs
"""

import re
import os
from pathlib import Path

def clean_print_statements(file_path):
    """Nettoyer les print statements d'un fichier"""

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Patterns de remplacement pour les print statements typiques
    replacements = [
        # Print statements avec emojis de débogage → commentaires
        (r'print\(f"🔄.*?\)\n', ''),
        (r'print\(f"✅.*?\)\n', ''),
        (r'print\(f"🔍.*?\)\n', ''),
        (r'print\(f"📊.*?\)\n', ''),
        (r'print\(f"🚀.*?\)\n', ''),
        (r'print\(f"🧠.*?\)\n', ''),
        (r'print\(f"✨.*?\)\n', ''),
        (r'print\(f"❌.*?\)\n', ''),

        # Print statements d'erreur → app_logger.error
        (r'print\(f"Erreur.*?{([^}]+)}.*?"\)', r'app_logger.error("Erreur", \1)'),

        # Print statements simples de débogage → commentaires ou suppression
        (r'print\(f"  🔄.*?\)\n', ''),
        (r'print\(f"   .*?\)\n', ''),

        # Messages de diagnostic batch → app_logger.debug
        (r'print\(f"BATCH.*?"\)', '# Batch processing'),
        (r'print\(f"MÉTHODE.*?"\)', '# Method call'),
    ]

    changes_made = 0

    for pattern, replacement in replacements:
        new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
        if count > 0:
            content = new_content
            changes_made += count

    # Nettoyer les lignes vides multiples
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)

    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ {file_path}: {changes_made} modifications")
        return changes_made
    else:
        print(f"⏸️  {file_path}: aucune modification")
        return 0

def main():
    """Nettoyer tous les fichiers Python"""

    src_dir = Path("/Users/emg1/Desktop/1001 projects/1001pieces_autofill Claude/src")

    total_changes = 0
    files_modified = 0

    print("🧹 Nettoyage automatique des print statements...")
    print("=" * 60)

    # Nettoyer tous les fichiers .py
    for py_file in src_dir.rglob("*.py"):
        try:
            changes = clean_print_statements(py_file)
            if changes > 0:
                total_changes += changes
                files_modified += 1
        except Exception as e:
            print(f"❌ Erreur avec {py_file}: {e}")

    print("=" * 60)
    print(f"📊 Résumé:")
    print(f"   Fichiers modifiés: {files_modified}")
    print(f"   Total modifications: {total_changes}")
    print("✅ Nettoyage terminé!")

if __name__ == "__main__":
    main()