import json
from pathlib import Path

from .models import (
    AgentCapability,
    AgentContractDefinition,
    AgentDefinition,
    AgentTeamDefinition,
    AgentTeamWorkflowStep,
)


class AgentRegistry:
    def get_agent(self, agent_id: str) -> AgentDefinition:
        raise NotImplementedError

    def list_agents(self) -> list[AgentDefinition]:
        raise NotImplementedError

    def find_by_capability(self, capability: str) -> list[AgentDefinition]:
        raise NotImplementedError

    def get_team(self, team_id: str) -> AgentTeamDefinition:
        raise NotImplementedError

    def resolve_entrypoint(self, task_type: str) -> str:
        raise NotImplementedError


class FileAgentRegistry(AgentRegistry):
    def __init__(self, registry_path: Path | None = None):
        self._registry_path = registry_path or Path(__file__).with_name("definitions.json")
        payload = json.loads(self._registry_path.read_text(encoding="utf-8"))

        self._capabilities = {
            item["capability_id"]: AgentCapability(
                capability_id=item["capability_id"],
                name=item["name"],
                description=item.get("description", ""),
            )
            for item in payload.get("capabilities", [])
        }
        self._agents = {
            item["agent_id"]: AgentDefinition(
                agent_id=item["agent_id"],
                name=item["name"],
                capability_ids=tuple(item.get("capability_ids", [])),
                input_contract=AgentContractDefinition(**item["input_contract"]),
                output_contract=AgentContractDefinition(**item["output_contract"]),
                handler_id=item["handler_id"],
                task_types=tuple(item.get("task_types", [])),
                team_id=item.get("team_id"),
            )
            for item in payload.get("agents", [])
        }
        self._teams = {
            item["team_id"]: AgentTeamDefinition(
                team_id=item["team_id"],
                name=item["name"],
                agent_ids=tuple(item.get("agent_ids", [])),
                entry_agent_id=item["entry_agent_id"],
                task_types=tuple(item.get("task_types", [])),
                workflow_steps=tuple(
                    AgentTeamWorkflowStep(
                        step_id=step["step_id"],
                        agent_id=step["agent_id"],
                        input_contract_id=step["input_contract_id"],
                        output_contract_id=step["output_contract_id"],
                        handoff_to=step.get("handoff_to"),
                        optional=bool(step.get("optional", False)),
                        description=step.get("description", ""),
                    )
                    for step in item.get("workflow_steps", [])
                ),
            )
            for item in payload.get("teams", [])
        }
        self._entrypoints = payload.get("entrypoints", {})

    def get_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent_id: {agent_id}") from exc

    def list_agents(self) -> list[AgentDefinition]:
        return list(self._agents.values())

    def find_by_capability(self, capability: str) -> list[AgentDefinition]:
        capability_id = capability.strip().lower()
        return [
            agent
            for agent in self._agents.values()
            if capability_id in {item.lower() for item in agent.capability_ids}
        ]

    def get_team(self, team_id: str) -> AgentTeamDefinition:
        try:
            return self._teams[team_id]
        except KeyError as exc:
            raise KeyError(f"unknown team_id: {team_id}") from exc

    def resolve_entrypoint(self, task_type: str) -> str:
        normalized = task_type.strip().lower()
        entrypoint = self._entrypoints.get(normalized) or self._entrypoints.get("default")
        if not entrypoint:
            raise KeyError(f"no entrypoint configured for task_type: {task_type}")
        return str(entrypoint)
