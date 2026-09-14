"""Durable regression guard: assemble_prompt must never gain a parameter typed
as raw interoceptive/affective/self-model state. This is the project's most
important invariant (spec: "do not build a costume") -- catch it here, not in
review, if someone "improves" prompt assembly later."""

from __future__ import annotations

import inspect

from teic.llm import prompt_assembly


def test_assemble_prompt_has_no_raw_state_parameter() -> None:
    sig = inspect.signature(prompt_assembly.assemble_prompt)
    for name, param in sig.parameters.items():
        annotation = param.annotation
        annotation_name = getattr(annotation, "__name__", str(annotation))
        assert annotation_name not in prompt_assembly.FORBIDDEN_PARAM_TYPES, (
            f"assemble_prompt gained a raw-state parameter '{name}: {annotation_name}' -- "
            "prompts must be assembled ONLY from broadcast content."
        )
