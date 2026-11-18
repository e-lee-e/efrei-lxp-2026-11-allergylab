"""Garde-fous communs aux tests de l'équipe (CLAUDE.md, section « Tests »).

Ces trois protections se déclenchent seules dans chaque fichier de test qui les
importe : un test ne peut ni sortir sur le réseau, ni lire la vraie clé, ni
ouvrir le fichier de données réel. S'il essaie, il échoue avec un message qui
dit quoi faire.

Ce fichier ne s'appelle pas conftest.py à dessein : les tests du kit font
« from conftest import … » et doivent retrouver celui de kit/tests/.
"""

import socket

import pandas as pd
import pytest

from kit import cle
from kit.donnees import RACINE

CONNEXION_REELLE = socket.socket.connect
LECTURE_REELLE = pd.read_csv


@pytest.fixture(autouse=True)
def sans_reseau(monkeypatch):
    """Aucune connexion hors de la machine : le modèle ne se joue qu'avec un modèle scripté."""

    def refuser(prise, adresse, *arguments):
        if isinstance(adresse, tuple) and adresse[0] in ("127.0.0.1", "::1"):  # liaison interne de Python sous Windows
            return CONNEXION_REELLE(prise, adresse, *arguments)
        raise RuntimeError("Un test a tenté une connexion réseau. Utilise un modèle scripté (voir test_agent.py).")

    monkeypatch.setattr(socket.socket, "connect", refuser)


@pytest.fixture(autouse=True)
def sans_vraie_cle(tmp_path, monkeypatch):
    """Un dossier personnel vide pour la clé, et aucune variable de clé : la vraie clé reste intouchable."""
    monkeypatch.setattr(cle, "fichier", lambda: tmp_path / "maison" / ".allergylab" / "cle")
    monkeypatch.delenv(cle.VARIABLE, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def sans_fichier_reel(monkeypatch):
    """Les tests lisent la table inventée de kit/exemple/, jamais le fichier de donnees/."""

    def lire(chemin, *arguments, **options):
        if (RACINE / "donnees") in getattr(chemin, "parents", ()) or "donnees" in str(chemin).replace("\\", "/").split("/"):
            raise RuntimeError("Un test a ouvert un fichier de donnees/. Lis la table inventée kit/exemple/mini.csv.")
        return LECTURE_REELLE(chemin, *arguments, **options)

    monkeypatch.setattr(pd, "read_csv", lire)


@pytest.fixture(autouse=True)
def sans_vrai_cache(tmp_path, monkeypatch):
    """Le cache de réponses vit dans un dossier jetable : un test n'écrit pas dans ~/.allergylab/cache."""
    from equipe import cache

    monkeypatch.setattr(cache, "DOSSIER", tmp_path / "cache")
