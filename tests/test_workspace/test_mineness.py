from teic.models.workspace import WorkspaceCandidate
from teic.workspace.mineness import mineness_tag


def _candidate(source: str) -> WorkspaceCandidate:
    return WorkspaceCandidate(
        source_module=source,
        content={},
        novelty=0.5,
        precision=0.5,
        affective_weight=0.5,
        goal_relevance=0.5,
    )


def test_interoception_and_memory_are_self():
    assert mineness_tag(_candidate("interoception")) == "self"
    assert mineness_tag(_candidate("memory")) == "self"


def test_user_message_is_other():
    assert mineness_tag(_candidate("user_message")) == "other"


def test_viability_is_self():
    assert mineness_tag(_candidate("viability")) == "self"
