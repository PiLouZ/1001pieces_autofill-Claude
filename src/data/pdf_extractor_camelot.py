#!/usr/bin/env python3
"""
Extracteur PDF basé sur Camelot-Py pour extraction de tableaux
Remplace les anciennes méthodes pdfplumber
"""

import camelot
import pandas as pd
import os
import re
from typing import List, Tuple, Dict, Any, Optional, Callable
from pathlib import Path
from src.utils.error_handler import handle_pdf_extraction_errors

class PDFExtractionError(Exception):
    """Exception levée lors d'erreurs d'extraction PDF"""
    pass

# Nombre de pages traitées par lot lors de l'extraction complète,
# pour permettre une progression visible sur les gros PDF
PAGES_CHUNK_SIZE = 10

class CamelotPDFExtractor:
    """Extracteur PDF basé sur Camelot-Py"""
    
    def __init__(self):
        self.last_extraction_info = None
        self.debug_mode = False
    
    def extract_data(self, pdf_path: str, preview_mode: bool = False,
                      progress_cb: Optional[Callable] = None,
                      cancel_check: Optional[Callable] = None) -> List[List[str]]:
        """
        Extraire les données d'un PDF avec Camelot-Py

        Args:
            pdf_path: Chemin vers le fichier PDF
            preview_mode: Si True, extrait seulement la 1ère page (aperçu rapide)
            progress_cb: callable(page, total_pages) appelé entre chaque lot de pages
                         (extraction complète uniquement)
            cancel_check: callable() -> bool, permet d'interrompre l'extraction entre deux lots

        Returns:
            Liste de listes contenant les données extraites [ref_technique, ref_commerciale, description]

        Notes:
            PHASE 1 OPTIMISATION: preview_mode=True réduit le temps de 90%
            en chargeant seulement la 1ère page pour l'aperçu dialogue
        """
        return self._safe_extract_data_core(pdf_path, preview_mode, progress_cb, cancel_check)

    @handle_pdf_extraction_errors(return_value=[])
    def _safe_extract_data_core(self, pdf_path: str, preview_mode: bool = False,
                                 progress_cb: Optional[Callable] = None,
                                 cancel_check: Optional[Callable] = None) -> List[List[str]]:
        """Noyau sécurisé pour l'extraction de données PDF"""
        try:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                raise PDFExtractionError(f"Fichier non trouvé: {pdf_path}")

            if not pdf_path.suffix.lower() == '.pdf':
                raise PDFExtractionError(f"Le fichier doit être un PDF: {pdf_path}")

            return self._extract_with_camelot(pdf_path, preview_mode, progress_cb, cancel_check)

        except Exception as e:
            if "camelot" in str(e).lower():
                raise PDFExtractionError(f"Erreur Camelot: {e}")
            else:
                raise PDFExtractionError(f"Erreur lors de l'extraction: {e}")

    def _count_pdf_pages(self, pdf_path: Path) -> int:
        """Compter le nombre de pages d'un PDF via pdfminer (déjà une dépendance de Camelot)"""
        try:
            from pdfminer.pdfpage import PDFPage
            with open(pdf_path, 'rb') as f:
                return sum(1 for _ in PDFPage.get_pages(f))
        except Exception:
            return 1

    def _extract_with_camelot(self, pdf_path: Path, preview_mode: bool = False,
                               progress_cb: Optional[Callable] = None,
                               cancel_check: Optional[Callable] = None) -> List[List[str]]:
        """
        Extraction avec Camelot-Py sur toutes les pages (ou 1ère page en mode preview)
        """
        all_data = []
        extraction_stats = {
            'total_pages': 0,
            'valid_pages': 0,
            'invalid_pages': 0,
            'total_rows': 0,
            'filename': pdf_path.name,
            'extraction_method': 'camelot',
            'preview_mode': preview_mode
        }

        return self._safe_extract_with_camelot_core(pdf_path, all_data, extraction_stats, preview_mode,
                                                      progress_cb, cancel_check)

    @handle_pdf_extraction_errors(return_value=[])
    def _safe_extract_with_camelot_core(self, pdf_path: Path, all_data: List, extraction_stats: Dict,
                                         preview_mode: bool = False,
                                         progress_cb: Optional[Callable] = None,
                                         cancel_check: Optional[Callable] = None) -> List[List[str]]:
        """Noyau sécurisé pour l'extraction avec Camelot"""
        try:
            # PHASE 1 OPTIMISATION: Mode preview charge seulement la 1ère page (10x plus rapide)
            pages_param = '1' if preview_mode else 'all'

            total_pages = 1 if preview_mode else self._count_pdf_pages(pdf_path)

            if not preview_mode and total_pages > PAGES_CHUNK_SIZE:
                # PHASE 2 OPTIMISATION: extraction par lots de pages pour permettre
                # une progression visible (et une annulation possible) sur les gros PDF
                tables = []
                for start in range(1, total_pages + 1, PAGES_CHUNK_SIZE):
                    if cancel_check and cancel_check():
                        break
                    end = min(start + PAGES_CHUNK_SIZE - 1, total_pages)
                    chunk_tables = camelot.read_pdf(str(pdf_path), flavor='stream',
                                                     pages=f"{start}-{end}", edge_tol=500)
                    tables.extend(chunk_tables)
                    if progress_cb:
                        progress_cb(end, total_pages)

                if len(tables) == 0:
                    # Fallback global stream/lattice (rare, document atypique)
                    tables = camelot.read_pdf(str(pdf_path), flavor='stream', pages='all')
                    if len(tables) == 0:
                        tables = camelot.read_pdf(str(pdf_path), flavor='lattice', pages='all')
            else:
                # Essayer d'abord avec la méthode 'stream' optimisée (basée sur les espaces)
                # edge_tol=500 permet de capturer les lignes avec caractères spéciaux
                tables = camelot.read_pdf(str(pdf_path), flavor='stream', pages=pages_param, edge_tol=500)

                if len(tables) == 0:
                    # Fallback vers stream standard
                    tables = camelot.read_pdf(str(pdf_path), flavor='stream', pages=pages_param)

                if len(tables) == 0:
                    # Fallback final vers 'lattice' si stream ne trouve rien
                    tables = camelot.read_pdf(str(pdf_path), flavor='lattice', pages=pages_param)

            if len(tables) == 0:
                raise PDFExtractionError("Aucun tableau détecté dans le PDF")

            extraction_stats['total_pages'] = len(tables)

            if self.debug_mode:
                print(f" Camelot: {len(tables)} tableaux détectés")

            # Traiter chaque tableau (page)
            plages_par_page = {}
            for i, table in enumerate(tables):
                page_num = i + 1
                debut = len(all_data)
                self._safe_process_table_page(table, page_num, all_data, extraction_stats)
                self._noter_plage_page(table, debut, len(all_data), plages_par_page)

            extraction_stats['pages_vides'] = self._traiter_pages_vides(all_data, plages_par_page)
            extraction_stats['total_rows'] = len(all_data)
            self.last_extraction_info = extraction_stats
            return all_data

        except Exception as e:
            raise PDFExtractionError(f"Erreur Camelot: {e}")

    @staticmethod
    def _reference_de_ligne(ligne: List[str]) -> str:
        """Référence technique de la ligne, ou commerciale à défaut"""
        return ligne[0] or ligne[1]

    @staticmethod
    def _noter_plage_page(table, debut: int, fin: int, plages_par_page: Dict) -> None:
        """
        Retenir la plage [debut, fin) des lignes extraites d'une page.
        Une page peut porter plusieurs tableaux (consécutifs) : on étend la plage.
        """
        if fin <= debut:
            return
        try:
            page = int(table.page)
        except (AttributeError, TypeError, ValueError):
            return
        if page in plages_par_page:
            plages_par_page[page][1] = fin
        else:
            plages_par_page[page] = [debut, fin]

    @staticmethod
    def _retablir_tiret(reference: str, voisines: List[str]) -> Optional[str]:
        """
        `DFI746U 04` → `DFI746U-04` si une voisine commence par `DFI746U-`.

        La dernière ligne d'une page tronquée à l'impression peut perdre son tiret
        (le caractère est coupé, les deux morceaux restent). Sans voisine de même
        forme on ne devine pas : une espace peut être légitime ailleurs.
        """
        m = re.fullmatch(r'(\S+) (\S+)', reference)
        if not m:
            return None
        prefixe = m.group(1) + '-'
        if any(v.startswith(prefixe) for v in voisines if v):
            return prefixe + m.group(2)
        return None

    def _traiter_pages_vides(self, all_data: List[List[str]],
                             plages_par_page: Dict) -> List[Dict[str, Any]]:
        """
        Repérer les pages vides et réparer les lignes qui les bordent.

        Seules les deux lignes collées à un trou (dernière avant, première après)
        sont examinées : c'est là que l'impression a coupé une ligne en deux.
          - réf. technique vide (sa réf. est tombée sur la page perdue) : ligne
            retirée — importée, elle créait un appareil sans réf. technique,
            doublon de l'appareil complet présent dans l'autre version du PDF ;
          - tiret perdu (`DFI746U 04`) : rétabli si une voisine le confirme.
        Chaque réparation est jointe au trou concerné, pour être affichée.
        """
        pages = sorted(plages_par_page)
        trous = [(p, s) for p, s in zip(pages, pages[1:]) if s - p > 1]
        if not trous:
            return []

        a_retirer = set()
        reparations = {}
        for precedente, suivante in trous:
            corrections, ignorees = [], []
            bord_avant = plages_par_page[precedente][1] - 1
            bord_apres = plages_par_page[suivante][0]
            for i, vis_a_vis in ((bord_avant, bord_apres), (bord_apres, bord_avant)):
                ligne = all_data[i]
                if not ligne[0]:
                    if i not in a_retirer:
                        a_retirer.add(i)
                        ignorees.append(' '.join(c for c in ligne if c))
                    continue
                voisines = [all_data[j][0] for j in (i - 1, i + 1, vis_a_vis)
                            if 0 <= j < len(all_data) and j != i]
                corrigee = self._retablir_tiret(ligne[0], voisines)
                if corrigee:
                    corrections.append((ligne[0], corrigee))
                    ligne[0] = corrigee
            reparations[precedente] = {'corrections': corrections, 'ignorees': ignorees}

        # Bornes calculées après réparation : une ligne retirée n'en est pas une
        bornes_par_page = {}
        for page, (debut, fin) in plages_par_page.items():
            refs = [self._reference_de_ligne(all_data[i]) for i in range(debut, fin)
                    if i not in a_retirer]
            refs = [r for r in refs if r]
            if refs:
                bornes_par_page[page] = (refs[0], refs[-1])

        resultat = self._detecter_pages_vides(bornes_par_page)
        for trou in resultat:
            for cle, valeurs in reparations.get(trou['pages'][0] - 1, {}).items():
                if valeurs:
                    trou[cle] = valeurs

        for i in sorted(a_retirer, reverse=True):
            del all_data[i]
        return resultat

    @staticmethod
    def _detecter_pages_vides(bornes_par_page: Dict) -> List[Dict[str, Any]]:
        """
        Repérer les pages sans aucune donnée situées ENTRE deux pages qui en ont.

        Cas réel (805101, « Microsoft: Print To PDF ») : le contenu débordant d'une
        page est perdu et la page suivante sort blanche — 13 appareils absents du
        fichier. On ne peut pas les récupérer, mais la dernière référence lue avant
        le trou et la première lue après donnent la fourchette où les chercher.
        Les pages vides en début ou en fin de fichier (garde, saut final) sont
        ignorées : elles n'interrompent aucune suite de données.

        Returns:
            [{'pages': [3], 'avant': 'DFI544BXXL-04', 'apres': 'DFI544D-02'}, ...]
        """
        pages = sorted(bornes_par_page)
        trous = []
        for precedente, suivante in zip(pages, pages[1:]):
            if suivante - precedente > 1:
                trous.append({
                    'pages': list(range(precedente + 1, suivante)),
                    'avant': bornes_par_page[precedente][1],
                    'apres': bornes_par_page[suivante][0],
                })
        return trous

    @handle_pdf_extraction_errors()
    def _safe_process_table_page(self, table, page_num: int, all_data: List, extraction_stats: Dict) -> None:
        """Traiter une page de tableau de manière sécurisée"""
        # Convertir en DataFrame pandas
        df = table.df

        if df.empty:
            extraction_stats['invalid_pages'] += 1
            return

        # Nettoyer les données de cette page
        self._fragments_recolles_page = 0
        page_data = self._clean_page_data(df, page_num)
        extraction_stats['fragments_recolles'] = (extraction_stats.get('fragments_recolles', 0)
                                                  + self._fragments_recolles_page)

        if page_data:
            all_data.extend(page_data)
            extraction_stats['valid_pages'] += 1
            extraction_stats['total_rows'] += len(page_data)

            if self.debug_mode:
                print(f"  Page {page_num}: {len(page_data)} lignes extraites")
        else:
            extraction_stats['invalid_pages'] += 1
    
    def _clean_page_data(self, df: pd.DataFrame, page_num: int) -> List[List[str]]:
        """
        Nettoyer les données d'une page
        """
        cleaned_data = []
        
        # Convertir DataFrame en liste de listes
        raw_data = df.values.tolist()
        
        if not raw_data:
            return []
        
        # Supprimer les lignes d'en-tête
        filtered_data = []
        for row in raw_data:
            # Nettoyer la ligne
            cleaned_row = [str(cell).strip() if cell is not None else '' for cell in row]
            
            # Vérifier si c'est une ligne d'en-tête
            if self._is_header_row(cleaned_row):
                if self.debug_mode:
                    print(f"En-tête détecté et ignoré: {cleaned_row}")
                continue

            # Vérifier si c'est une ligne de pagination
            if self._is_pagination_row(cleaned_row):
                if self.debug_mode:
                    print(f"Pagination détectée et ignorée: {cleaned_row}")
                continue
            
            # Garder les lignes avec du contenu
            if any(cell.strip() for cell in cleaned_row):
                filtered_data.append(cleaned_row)
        
        # Traiter les données filtrées
        for row in filtered_data:
            # Assurer exactement 3 colonnes
            while len(row) < 3:
                row.append('')
            row = row[:3]
            
            # Nettoyer chaque cellule
            cleaned_row = []
            for cell in row:
                # Sécuriser contre les valeurs None
                if cell is None:
                    cleaned_cell = ''
                else:
                    cleaned_cell = str(cell).strip()
                    # Supprimer les astérisques en début
                    if cleaned_cell.startswith('*'):
                        cleaned_cell = cleaned_cell[1:].strip()
                cleaned_row.append(cleaned_cell)
            
            # Garder les lignes qui ont du contenu utile (au moins une cellule non vide)
            # Plus permissif comme l'import manuel
            if any(cell.strip() if cell else False for cell in cleaned_row):
                cleaned_data.append(cleaned_row)

        return self._recoller_fragments(cleaned_data)

    # Mots qui composent un en-tête de colonne coupé sur plusieurs lignes
    # (ex. "Réf." / "commerciale"), jamais une donnée à eux seuls
    MOTS_EN_TETE_FRAGMENTE = {'réf.', 'réf', 'ref.', 'ref', 'technique',
                              'commerciale', 'description'}

    def _recoller_fragments(self, rows: List[List[str]]) -> List[List[str]]:
        """
        Recoller les lignes éclatées par une cellule haute (texte sur 2 lignes,
        contenu centré verticalement) et retirer les en-têtes fragmentés.

        Motifs reconnus, uniquement s'ils sont complets (3 lignes consécutives) :
          - description scindée : [∅,∅,D1] [R,C,∅] [∅,∅,D2]  → [R, C, "D1 D2"]
          - réf. technique coupée : [R1-,∅,∅] [∅,C,D] [R2,∅,∅] → [R1R2, C, D]
        Une ligne complète ou sans description n'entre dans aucun motif :
        les PDF bien formés ressortent inchangés.
        """
        forme = lambda r: (bool(r[0]), bool(r[1]), bool(r[2]))
        resultat = []
        recollages = 0
        i = 0
        while i < len(rows):
            row = rows[i]
            cellules = [c for c in row if c]
            if cellules and all(c.lower() in self.MOTS_EN_TETE_FRAGMENTE for c in cellules):
                i += 1
                continue

            if i + 2 < len(rows):
                haut, milieu, bas = row, rows[i + 1], rows[i + 2]
                f_haut, f_milieu, f_bas = forme(haut), forme(milieu), forme(bas)

                if f_haut == f_bas == (False, False, True) and f_milieu == (True, True, False):
                    resultat.append([milieu[0], milieu[1], f"{haut[2]} {bas[2]}"])
                    recollages += 1
                    i += 3
                    continue

                if (f_haut == f_bas == (True, False, False) and haut[0].endswith('-')
                        and f_milieu == (False, True, True)):
                    resultat.append([haut[0] + bas[0], milieu[1], milieu[2]])
                    recollages += 1
                    i += 3
                    continue

            resultat.append(row)
            i += 1

        self._fragments_recolles_page = recollages
        if self.debug_mode and recollages:
            print(f"  {recollages} ligne(s) éclatée(s) recollée(s)")
        return resultat
    
    def _is_header_row(self, row: List[str]) -> bool:
        """
        Vérifier si une ligne est un en-tête en utilisant une regex précise
        Basé sur la regex utilisateur : ^(Réf.*|Page.*)\n?
        """
        # Joindre la ligne et nettoyer
        row_text = ' '.join(row).strip()

        # Détection spécifique pour lignes d'en-têtes communes
        header_terms = [
            'réf. technique', 'réf. commerciale', 'ref technique', 'ref commerciale',
            'référence technique', 'référence commerciale', 'page',
            'designation', 'description', 'libellé'
        ]

        # Vérifier si la ligne contient principalement des termes d'en-têtes
        row_lower = row_text.lower()
        if any(term in row_lower for term in header_terms):
            # Vérifier que ce n'est pas une vraie donnée (pas de chiffres/codes produit)
            if not re.search(r'\b\d{3,}\b', row_text):  # Pas de codes à 3+ chiffres
                return True

        # Regex pour détecter les en-têtes de colonnes
        header_pattern = r'^(Réf\.?\s*(technique|commerciale|Technique|Commerciale)|Page.*|REFERENCE|REF\.|Référence)'

        return bool(re.match(header_pattern, row_text, re.IGNORECASE))
    
    def _is_pagination_row(self, row: List[str]) -> bool:
        """
        Vérifier si une ligne est une pagination en utilisant une regex précise
        Basé sur la regex utilisateur : ^(Réf.*|Page.*)\n?
        """
        # Joindre la ligne et nettoyer
        row_text = ' '.join(row).strip()
        
        # Regex précise pour détecter les vraies lignes de pagination
        # Ne supprime que les lignes commençant par "Page"
        pagination_pattern = r'^Page.*'
        
        return bool(re.match(pagination_pattern, row_text, re.IGNORECASE))
    
    
    @handle_pdf_extraction_errors(return_value=(False, "Erreur de validation PDF"))
    def validate_pdf_compatibility(self, pdf_path: str) -> Tuple[bool, str]:
        """
        Vérifier rapidement si un PDF est compatible avec Camelot
        """
        # Test rapide avec une seule page
        tables = camelot.read_pdf(pdf_path, flavor='stream', pages='1')

        if len(tables) == 0:
            # Essayer avec lattice
            tables = camelot.read_pdf(pdf_path, flavor='lattice', pages='1')

        if len(tables) > 0:
            return True, (f"PDF compatible - {len(tables)} "
                          f"{'tableau détecté' if len(tables) <= 1 else 'tableaux détectés'}")
        else:
            return False, "Aucun tableau détecté - Essayez l'import CSV ou le collage de données"