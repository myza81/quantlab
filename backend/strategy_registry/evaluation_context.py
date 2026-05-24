"""
EvaluationContext Descriptor Models — Phase 2O.6.

Passive Pydantic contracts describing what an EvaluationContext is expected
to provide and what an EvaluationPlan requires from a context.

These are metadata-only descriptors used for:
    - contract documentation
    - dependency pre-flight checking
    - context completeness validation before evaluation begins

No market data is loaded here. No indicators are computed here.

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.backtesting
    backend.execution
    backend.forward_testing
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.strategy_registry.semantic_plan import DependencySet


class EvaluationContextDescriptor(BaseModel):
    """
    Passive descriptor of what an EvaluationContext declares it can provide.

    Used to pre-flight check context completeness against plan requirements
    before evaluation begins. Does NOT load or access actual values.

    A concrete EvaluationContext implementation must be able to satisfy
    all entries declared in its descriptor.
    """
    model_config = ConfigDict(frozen=True)

    evaluation_id:          str
    plan_draft_id:          str | None = None
    declared_tool_outputs:  tuple[str, ...]  # "instance_id.output_name" refs
    declared_price_fields:  tuple[str, ...]  # e.g. ("close", "open")
    declared_constants:     tuple[str, ...]  # numeric string refs


class EvaluationRequirements(BaseModel):
    """
    Passive descriptor of what an EvaluationPlan requires from its context.

    Derived from EvaluationPlan.dependencies — used to verify that a
    proposed context can satisfy the plan's declared dependency set.

    No evaluation occurs here. This is a pre-flight contract only.
    """
    model_config = ConfigDict(frozen=True)

    required_tool_outputs: tuple[str, ...]
    required_price_fields: tuple[str, ...]
    required_constants:    tuple[str, ...]


class ContextSatisfactionReport(BaseModel):
    """
    Passive report of whether a context satisfies a plan's requirements.

    satisfied=True   → all required dependencies are declared by the context
    satisfied=False  → at least one required dependency is missing
    missing:         → the unsatisfied requirement refs
    """
    model_config = ConfigDict(frozen=True)

    satisfied:             bool
    missing_tool_outputs:  tuple[str, ...]
    missing_price_fields:  tuple[str, ...]
    missing_constants:     tuple[str, ...]


def extract_requirements(dependencies: DependencySet) -> EvaluationRequirements:
    """
    Extract EvaluationRequirements from a DependencySet.

    Pure function — reads the plan's declared dependencies into a requirements
    descriptor. Does NOT validate whether those dependencies are satisfiable.

    Args:
        dependencies: DependencySet from a compiled EvaluationPlan

    Returns:
        EvaluationRequirements describing what a context must provide.
    """
    return EvaluationRequirements(
        required_tool_outputs=dependencies.tool_outputs,
        required_price_fields=dependencies.price_fields,
        required_constants=dependencies.constants,
    )


def check_context_satisfaction(
    requirements: EvaluationRequirements,
    descriptor:   EvaluationContextDescriptor,
) -> ContextSatisfactionReport:
    """
    Check whether a context descriptor satisfies a set of requirements.

    Pure function — no evaluation, no data loading, no computation.
    Performs only set membership checks on declared/required ref strings.

    Args:
        requirements: Requirements derived from an EvaluationPlan
        descriptor:   Descriptor of what a proposed context provides

    Returns:
        ContextSatisfactionReport indicating whether all requirements are met.
    """
    declared_outputs = frozenset(descriptor.declared_tool_outputs)
    declared_prices  = frozenset(descriptor.declared_price_fields)
    declared_consts  = frozenset(descriptor.declared_constants)

    missing_outputs = tuple(
        r for r in requirements.required_tool_outputs if r not in declared_outputs
    )
    missing_prices = tuple(
        r for r in requirements.required_price_fields if r not in declared_prices
    )
    missing_consts = tuple(
        r for r in requirements.required_constants if r not in declared_consts
    )

    return ContextSatisfactionReport(
        satisfied=(
            not missing_outputs and not missing_prices and not missing_consts
        ),
        missing_tool_outputs=missing_outputs,
        missing_price_fields=missing_prices,
        missing_constants=missing_consts,
    )
