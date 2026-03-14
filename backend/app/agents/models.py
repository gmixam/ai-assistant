from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentCapability:
    capability_id: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class AgentContractDefinition:
    contract_id: str
    version: str
    description: str = ""


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    capability_ids: tuple[str, ...]
    input_contract: AgentContractDefinition
    output_contract: AgentContractDefinition
    handler_id: str
    task_types: tuple[str, ...] = ()
    team_id: str | None = None


@dataclass(frozen=True)
class AgentTeamDefinition:
    team_id: str
    name: str
    agent_ids: tuple[str, ...]
    entry_agent_id: str
    task_types: tuple[str, ...] = ()
    workflow_steps: tuple["AgentTeamWorkflowStep", ...] = ()


@dataclass(frozen=True)
class AgentTeamWorkflowStep:
    step_id: str
    agent_id: str
    input_contract_id: str
    output_contract_id: str
    handoff_to: str | None = None
    optional: bool = False
    description: str = ""


@dataclass(frozen=True)
class AgentInputContract:
    task_id: str
    task_type: str
    agent_id: str
    team_id: str | None
    input_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentOutputContract:
    task_id: str
    task_type: str
    agent_id: str
    team_id: str | None
    success: bool
    result_text: str | None = None
    error_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteResolution:
    task_type: str
    agent: AgentDefinition
    team: AgentTeamDefinition | None
