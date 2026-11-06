"""
Tests — Erreurs autrefois avalées en silence, désormais journalisées

Lot 2 du plan des restes post-audit : une vingtaine de `except Exception: pass`
(ou repli sans trace) reçoivent un `app_logger.debug/warning`. Le flux ne change
pas : même valeur de repli, aucune exception relancée. Ces tests provoquent
l'erreur sur deux sites représentatifs et vérifient les deux points.
"""

import io
import logging
from pathlib import Path

import pytest

from src.core.logger import app_logger
from src.services.import_relations import (
    Group, CardData, apply_relations, KIND_EQUIVALENCE,
)


@pytest.fixture
def messages_log():
    """Capture les messages du logger applicatif (même principe que
    test_paires_factorisees : handler explicite plutôt que caplog)."""
    tampon = io.StringIO()
    handler = logging.StreamHandler(tampon)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    niveau_origine = app_logger.logger.level
    app_logger.logger.addHandler(handler)
    app_logger.logger.setLevel(logging.DEBUG)
    try:
        yield lambda: tampon.getvalue().splitlines()
    finally:
        app_logger.logger.removeHandler(handler)
        app_logger.logger.setLevel(niveau_origine)


class _BaseRelations:
    """Double minimal : les trois primitives de relation réussissent."""

    def add_supersession(self, old, new):
        return True, ""

    def add_equivalence(self, a, b):
        return True, ""

    def mark_obsolete(self, ref):
        return True


class _BasePropagationEnPanne(_BaseRelations):
    def propagate_description(self, a, b):
        raise RuntimeError("base verrouillée")


class TestPropagationLibelle:

    def _appliquer(self, db):
        groupe = Group(KIND_EQUIVALENCE, members=["A", "B"])
        return apply_relations([groupe], [CardData(ref="A"), CardData(ref="B")], db)

    def test_echec_de_propagation_ne_change_pas_le_recap(self, messages_log):
        """La relation est créée, l'échec du libellé n'est pas une erreur de
        relation : récap identique à une base sans propagate_description."""
        assert self._appliquer(_BasePropagationEnPanne()) == self._appliquer(_BaseRelations())

    def test_echec_de_propagation_est_journalise(self, messages_log):
        self._appliquer(_BasePropagationEnPanne())
        lignes = [l for l in messages_log() if "Libellé non propagé" in l]
        assert lignes, messages_log()
        assert lignes[0].startswith("WARNING")
        assert "base verrouillée" in lignes[0]


class TestComptagePagesPdf:

    def test_pdf_illisible_suppose_une_page_et_le_journalise(self, tmp_path, messages_log):
        from src.data.pdf_extractor_camelot import CamelotPDFExtractor

        absent = Path(tmp_path) / "absent.pdf"
        assert CamelotPDFExtractor()._count_pdf_pages(absent) == 1
        assert any(l.startswith("DEBUG") and "Nombre de pages illisible" in l
                   for l in messages_log()), messages_log()
