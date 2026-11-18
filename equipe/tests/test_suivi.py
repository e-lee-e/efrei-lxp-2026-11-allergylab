"""Les questions de suivi (« et de femmes ? ») redeviennent des questions entières."""

from equipe import agent, suivi


def test_une_question_courte_qui_commence_par_et_est_un_suivi():
    assert suivi.est_suivi("et de femmes ?")
    assert suivi.est_suivi("Et pour les hommes ?")
    assert suivi.est_suivi("idem pour les villes")
    assert not suivi.est_suivi("Combien de patients ont plus de 60 ans ?")
    assert not suivi.est_suivi("")


def test_le_groupe_est_remplace_avec_la_bonne_preposition():
    assert suivi.resoudre("et de femmes ?", "Combien d'hommes compte le tableau ?") == (
        "Combien de femmes compte le tableau ?"
    )
    assert suivi.resoudre("et des hommes ?", "Quel est l'âge médian des femmes ?") == (
        "Quel est l'âge médian des hommes ?"
    )
    # On ne touche pas au reste de la phrase, accents et majuscules compris.
    assert suivi.resoudre("et des villes ?", "Combien de patients habitent les zones rurales ?") == (
        "Combien de patients habitent les villes ?"
    )


def test_un_groupe_inconnu_ne_se_devine_pas():
    """Mieux vaut avouer que reconstruire une question fausse."""
    assert suivi.resoudre("et pour les enfants ?", "Combien de femmes sont sensibilisées ?") is None
    assert suivi.resoudre("et de femmes ?", None) is None
    assert suivi.resoudre("combien de femmes ?", "Combien d'hommes ?") is None


def test_un_suivi_non_resolu_rend_une_abstention_sans_appel(monkeypatch):
    """Aucune question ne part au modèle si elle ne se tient pas debout."""

    def interdit(*args, **kwargs):
        raise AssertionError("aucun appel au modèle ne doit avoir lieu")

    monkeypatch.setattr(agent, "_repondre", interdit)
    sortie = agent.repondre("et pour les enfants ?", "Combien de femmes sont sensibilisées ?")
    assert sortie["statut"] == "abstention"
    assert "en entier" in sortie["justification"]
    assert agent.modele.journal.get("cause") == "suivi"
