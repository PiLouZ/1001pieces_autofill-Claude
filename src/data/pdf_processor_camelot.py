#!/usr/bin/env python3
"""
Processeur PDF final utilisant Camelot-Py
Remplace les anciennes méthodes
"""

import sys
from pathlib import Path
import argparse
from typing import List, Dict, Any

from pdf_extractor_camelot import CamelotPDFExtractor, PDFExtractionError

class CamelotPDFProcessor:
    """Processeur PDF utilisant Camelot-Py"""
    
    def __init__(self, debug: bool = False):
        self.extractor = CamelotPDFExtractor()
        self.extractor.debug_mode = debug
        self.results = []
    
    def process_single_pdf(self, pdf_path: str, output_format: str = "simple") -> Dict[str, Any]:
        """
        Traiter un seul PDF avec Camelot-Py
        """
        pdf_path = Path(pdf_path)
        result = {
            'filename': pdf_path.name,
            'success': False,
            'data': [],
            'error': None,
            'stats': None
        }
        
        try:
            # Validation
            is_compatible, message = self.extractor.validate_pdf_compatibility(str(pdf_path))
            if not is_compatible:
                result['error'] = f"PDF non compatible: {message}"
                return result
            
            # Extraction avec Camelot
            data = self.extractor.extract_data(str(pdf_path))
            
            if not data:
                result['error'] = "Aucune donnée extraite"
                return result
            
            # Succès
            result['success'] = True
            result['data'] = data
            result['stats'] = self.extractor.get_last_extraction_info()
            
            # Export CSV
            output_filename = f"{pdf_path.stem}_camelot_extracted.csv"
            include_metadata = (output_format == "detailed")
            
            self.extractor.export_to_csv(
                data, 
                output_filename, 
                include_metadata=include_metadata
            )
            
            result['output_file'] = output_filename
            
        except PDFExtractionError as e:
            result['error'] = f"Erreur d'extraction: {e}"
        except Exception as e:
            result['error'] = f"Erreur inattendue: {e}"
        
        return result
    
    def process_multiple_pdfs(self, pdf_paths: List[str], output_format: str = "simple") -> List[Dict[str, Any]]:
        """
        Traiter plusieurs fichiers PDF
        """
        results = []
        
        print(f"🐪 Traitement Camelot de {len(pdf_paths)} fichiers PDF...")
        
        for i, pdf_path in enumerate(pdf_paths, 1):
            print(f"[{i}/{len(pdf_paths)}] {Path(pdf_path).name}...")
            
            result = self.process_single_pdf(pdf_path, output_format)
            results.append(result)
            
            if result['success']:
                stats = result['stats']
                print(f"  ✅ {stats['total_rows']} lignes extraites ({stats['total_pages']} pages)")
            else:
                print(f"  ❌ {result['error']}")
        
        self.results = results
        return results
    
    def process_directory(self, pdf_directory: str, output_format: str = "simple") -> List[Dict[str, Any]]:
        """
        Traiter tous les PDFs d'un répertoire
        """
        pdf_dir = Path(pdf_directory)
        
        if not pdf_dir.exists() or not pdf_dir.is_dir():
            raise ValueError(f"Répertoire non trouvé: {pdf_directory}")
        
        pdf_files = list(pdf_dir.glob("*.pdf"))
        
        if not pdf_files:
            raise ValueError(f"Aucun fichier PDF trouvé dans {pdf_directory}")
        
        # Convertir en liste de chaînes
        pdf_paths = [str(pdf_file) for pdf_file in pdf_files]
        
        return self.process_multiple_pdfs(pdf_paths, output_format)
    
    def generate_summary_report(self, results: List[Dict[str, Any]]) -> str:
        """Générer un rapport de synthèse"""
        total_files = len(results)
        successful_files = sum(1 for r in results if r['success'])
        failed_files = total_files - successful_files
        
        total_rows = sum(len(r['data']) for r in results if r['success'])
        total_pages = sum(r['stats']['total_pages'] for r in results if r['success'] and r['stats'])
        
        report = f"""
🐪 RAPPORT DE TRAITEMENT PDF (Camelot-Py)
{'='*50}

📊 Statistiques globales:
  - Fichiers traités: {total_files}
  - Extractions réussies: {successful_files}
  - Échecs: {failed_files}
  - Taux de réussite: {(successful_files/total_files*100):.1f}%
  
📋 Données extraites:
  - Total lignes: {total_rows:,}
  - Total pages: {total_pages}
  - Moyenne lignes/fichier: {total_rows/successful_files:.1f} (si succès)

🔍 Détails par fichier:
"""
        
        for result in results:
            status = "✅" if result['success'] else "❌"
            if result['success']:
                stats = result['stats']
                detail = f"{len(result['data'])} lignes, {stats['total_pages']} pages"
            else:
                detail = result['error']
            
            report += f"  {status} {result['filename']}: {detail}\n"
        
        if failed_files > 0:
            report += f"\n⚠️ Fichiers en échec:\n"
            for result in results:
                if not result['success']:
                    report += f"  - {result['filename']}: {result['error']}\n"
        
        return report

def main():
    """Fonction principale"""
    parser = argparse.ArgumentParser(
        description="Extracteur PDF utilisant Camelot-Py"
    )
    parser.add_argument(
        "input", 
        help="Fichier PDF, liste de fichiers ou répertoire contenant les PDFs"
    )
    parser.add_argument(
        "--format", 
        choices=["simple", "detailed"], 
        default="simple",
        help="Format de sortie (défaut: simple)"
    )
    parser.add_argument(
        "--debug", 
        action="store_true",
        help="Mode debug avec informations détaillées"
    )
    parser.add_argument(
        "--report", 
        action="store_true",
        help="Générer un rapport de synthèse"
    )
    
    args = parser.parse_args()
    
    # Créer le processeur
    processor = CamelotPDFProcessor(debug=args.debug)
    
    try:
        input_path = Path(args.input)
        
        if input_path.is_file() and input_path.suffix.lower() == '.pdf':
            # Traitement d'un seul fichier
            print(f"🐪 Traitement Camelot du fichier: {input_path.name}")
            result = processor.process_single_pdf(str(input_path), args.format)
            
            if result['success']:
                stats = result['stats']
                                                                                            else:
                                sys.exit(1)
                
        elif input_path.is_dir():
            # Traitement d'un répertoire
            results = processor.process_directory(str(input_path), args.format)
            
            # Générer le rapport si demandé
            if args.report:
                report = processor.generate_summary_report(results)
                print(report)
                
                # Sauvegarder le rapport
                report_file = "pdf_extraction_camelot_report.txt"
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(report)
                print(f"📄 Rapport sauvegardé: {report_file}")
            
            # Statistiques finales
            successful = sum(1 for r in results if r['success'])
            total = len(results)
            print(f"\n🎯 Traitement terminé: {successful}/{total} fichiers réussis")
            
        else:
                        sys.exit(1)
            
    except Exception as e:
                sys.exit(1)

if __name__ == "__main__":
    main()