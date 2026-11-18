"""Tests des trois variantes de equipe/agent.py, sans réseau, sans clé, sans modèle.

Un modèle scripté joue le rôle du modèle : il rend, étape après étape, les
réponses qu'on lui a programmées. L'agent est le vrai, l'interpréteur de code
aussi : on vérifie ce que chaque variante peut et ne peut pas faire.
"""

import socket

import pytest
from smolagents import CodeAgent, ToolCallingAgent
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction, Model

from equipe import agent
from equipe.outils import calculer, chercher_colonne
from garde_fous import sans_fichier_reel, sans_reseau, sans_vraie_cle  # noqa: F401  (actifs d'office)
from kit import modele, reponse
from kit.donnees import RACINE, charger

class ModeleScripte(Model):
    """Rend les messages programmés, un par appel. Aucun réseau."""

    def __init__(self, *messages):
        super().__init__(model_id="scripte")
        self.messages = list(messages)

    def generate(self, messages, **options):
        return self.messages.pop(0)


def code(*lignes):
    """Un message du modèle qui écrit du code (CodeAgent)."""
    return ChatMessage(role="assistant", content="<code>\n" + "\n".join(lignes) + "\n</code>")


def appel(nom, **arguments):
    """Un message du modèle qui appelle un outil (ToolCallingAgent)."""
    fonction = ChatMessageToolCallFunction(name=nom, arguments=arguments)
    return ChatMessage(role="assistant", content="", tool_calls=[ChatMessageToolCall(id="1", type="function", function=fonction)])


@pytest.fixture
def mini(monkeypatch):
    """Les outils et l'agent lisent la table inventée au lieu du fichier réel."""
    tableau = charger(RACINE / "kit" / "exemple" / "mini.csv")
    for module in (calculer, chercher_colonne):
        monkeypatch.setattr(module, "tableau", lambda: tableau)
    monkeypatch.setattr(agent.cache, "tableau", lambda: tableau)
    modele.journal_neuf()
    return tableau


def jouer(monkeypatch, variante, *messages):
    """Pose une question à l'agent de cette variante, avec un modèle scripté."""
    monkeypatch.setattr(agent, "VARIANTE", variante)
    monkeypatch.setenv("ALLERGYLAB_RACCOURCIS", "0")  # l'agent seul : les couches locales répondraient à sa place
    monkeypatch.setattr(agent.modele, "ModeleKit", lambda: ModeleScripte(*messages))
    return reponse.valider(agent.repondre("Combien de lignes compte le tableau ?"))


def test_les_trois_variantes(mini, monkeypatch):
    monkeypatch.setattr(agent.modele, "ModeleKit", lambda: ModeleScripte())
    ouvert, ferme, outils = (agent.construire(v) for v in ("ouvert", "ferme", "outils"))
    assert isinstance(ouvert, CodeAgent) and "pandas" in ouvert.authorized_imports
    assert isinstance(ferme, CodeAgent) and "pandas" not in ferme.authorized_imports
    assert isinstance(outils, ToolCallingAgent)
    for variante in (ouvert, ferme, outils):
        assert {"calculer", "chercher_colonne"} <= set(variante.tools)


def test_variante_livree_valide_et_budget_du_kit(mini, monkeypatch):
    """La variante écrite dans agent.py existe, et les trois respectent les réglages du kit."""
    assert agent.VARIANTE in ("ouvert", "ferme", "outils")
    monkeypatch.setattr(agent.modele, "ModeleKit", lambda: ModeleScripte())
    for nom in ("ouvert", "ferme", "outils"):
        # Plafond maison à cinq étapes, décidé après mesure : huit étapes coûtent ~0,008 $.
        assert agent.construire(nom).max_steps == agent.ETAPES_MAX <= modele.REGLAGES["agent"]["etapes_max"]


def test_les_deux_lignes_d_acces_restent_visibles():
    """CLAUDE.md : les deux lignes qui ouvrent l'accès aux données restent commentées et faciles à retirer."""
    source = (RACINE / "equipe" / "agent.py").read_text(encoding="utf-8")
    assert "# Accès aux données (1/2)" in source and 'options["additional_authorized_imports"] = ["pandas"]' in source
    assert "# Accès aux données (2/2)" in source and 'arguments["tableau"] = cache.tableau()' in source


def test_garde_fous_actifs():
    """Les protections de conftest.py : fichier réel refusé, réseau refusé."""
    with pytest.raises(RuntimeError, match="donnees/"):
        charger()  # le fichier réel
    with pytest.raises(RuntimeError, match="réseau"):
        socket.create_connection(("example.com", 80), timeout=1)


def test_variante_inconnue(monkeypatch):
    monkeypatch.setenv("ALLERGYLAB_RACCOURCIS", "0")
    monkeypatch.setattr(agent, "VARIANTE", "ouverte")
    with pytest.raises(ValueError, match="ouvert"):
        agent.repondre("Une question ?")


def test_ouvert_voit_le_tableau(mini, monkeypatch):
    """Ouvert : le code reçoit le tableau sous le nom tableau et peut importer pandas."""
    sortie = jouer(monkeypatch, "ouvert", code(
        "import pandas as pd",
        "final_answer({'statut': 'reponse', 'valeur': len(tableau), 'justification': 'Douze lignes.'})",
    ))
    assert sortie["valeur"] == 12


def test_ferme_n_a_ni_pandas_ni_tableau(mini, monkeypatch):
    """Fermer l'accès : l'import est refusé, le tableau n'existe pas, l'outil répond encore."""
    sortie = jouer(
        monkeypatch, "ferme",
        code("import pandas as pd"),
        code("print(len(tableau))"),
        code("print(calculer(operation='compter'))"),
        code("final_answer({'statut': 'reponse', 'valeur': 12, 'justification': 'Douze lignes.'})"),
    )
    etapes = modele.journal["etapes"]
    assert "pandas" in etapes[0]["resultat"] and "not allowed" in etapes[0]["resultat"]
    assert "tableau" in etapes[1]["resultat"] and "Erreur" in etapes[1]["resultat"]
    assert "12 patients sur 12" in etapes[2]["resultat"]
    assert sortie["valeur"] == 12


def test_outils_n_execute_aucun_code(mini, monkeypatch):
    sortie = jouer(
        monkeypatch, "outils",
        appel("calculer", operation="compter"),
        appel("final_answer", answer={"statut": "reponse", "valeur": 12, "justification": "Douze lignes."}),
    )
    etapes = modele.journal["etapes"]
    assert etapes[0]["code"].startswith("calculer(") and "12 patients sur 12" in etapes[0]["resultat"]
    assert sortie["valeur"] == 12


def test_consigne_de_b_et_format_du_kit_dans_les_instructions(mini, monkeypatch):
    monkeypatch.setattr(agent.modele, "ModeleKit", lambda: ModeleScripte())
    consigne = agent.construire("ferme").instructions
    assert agent.CONSIGNE.strip() in consigne and reponse.FORMAT in consigne and "chercher_colonne" in consigne


def test_le_modele_est_bride_en_jetons_et_en_temps(monkeypatch):
    """Un plafond de sortie et un délai passent à chaque appel : sans eux, 128 000 jetons et six minutes."""
    vus = {}

    class Faux:
        def generate(self, messages, **options):
            vus.update(options)
            return "ok"

    monkeypatch.setattr(agent.modele, "ModeleKit", lambda: Faux())
    agent.modele_du_jour().generate([], max_tokens=50_000)
    assert vus["max_tokens"] == agent.SORTIE_MAX
    assert 0 < vus["timeout"] <= agent.DELAI_MAX


def test_une_question_trop_lente_rend_une_abstention_lisible(monkeypatch):
    """Au-delà du délai, la réponse est une abstention nette, pas une exception."""

    class Faux:
        def generate(self, messages, **options):
            return "ok"

    class AgentQuiAppelle:
        def run(self, question, additional_args=None):
            agent.modele_du_jour().generate([])  # lève DelaiDepasse

    monkeypatch.setattr(agent, "DELAI_MAX", 0.0)
    monkeypatch.setattr(agent, "VARIANTE", "ferme")
    monkeypatch.setattr(agent, "raccourcis", lambda: False)
    monkeypatch.setattr(agent.modele, "ModeleKit", lambda: Faux())
    monkeypatch.setattr(agent, "construire", lambda variante: AgentQuiAppelle())

    sortie = agent.repondre("une question qui ne finira pas")

    assert sortie["statut"] == "abstention"
    assert sortie["valeur"] is None
    assert "délai" in sortie["justification"]
    assert reponse.valider(sortie)


def test_deux_outils_seulement():
    """Chaque description d'outil est repayée à chaque étape : on n'en offre que deux, courtes."""
    assert [outil.name for outil in agent.OUTILS] == ["calculer", "chercher_colonne"]
    assert sum(len(outil.description) + len(str(outil.inputs)) for outil in agent.OUTILS) < 2600
