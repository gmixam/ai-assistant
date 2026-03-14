import logging
from dataclasses import asdict
from types import SimpleNamespace
from typing import Protocol

from sqlalchemy.orm import Session

from ..attachment_pipeline import prepare_task_execution_input
from ..executors.base import ExecutionResult, TaskExecutor
from ..models import Task, TaskAttachment
from .models import AgentDefinition, AgentInputContract, AgentOutputContract
from .registry import AgentRegistry

logger = logging.getLogger("execution_router")


class ExecutionHandler(Protocol):
    def execute(self, agent_input: AgentInputContract, executor: TaskExecutor) -> ExecutionResult:
        ...


class DocumentAnalysisExecutionHandler:
    def execute(self, agent_input: AgentInputContract, executor: TaskExecutor) -> ExecutionResult:
        execution_task = SimpleNamespace(
            id=agent_input.task_id,
            input_text=agent_input.input_text,
        )
        return executor.execute(execution_task)


class StubExecutionHandler:
    def __init__(self, handler_name: str):
        self._handler_name = handler_name

    def execute(self, agent_input: AgentInputContract, executor: TaskExecutor) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            result_text=(
                f"Stub handler {self._handler_name} prepared for task {agent_input.task_id} "
                f"agent={agent_input.agent_id} team={agent_input.team_id or 'none'}"
            ),
            error_text=None,
        )


class ExecutionRouter:
    def __init__(self, registry: AgentRegistry, handlers: dict[str, ExecutionHandler] | None = None):
        self._registry = registry
        self._handlers = handlers or {
            "legacy_document_analysis": DocumentAnalysisExecutionHandler(),
            "attachment_document_analysis_bridge": DocumentAnalysisExecutionHandler(),
            "email_triage_stub": StubExecutionHandler("email_triage_stub"),
            "action_extraction_stub": StubExecutionHandler("action_extraction_stub"),
            "approval_prep_stub": StubExecutionHandler("approval_prep_stub"),
        }

    def route(self, task: Task, db: Session, executor: TaskExecutor) -> AgentOutputContract:
        task_type = self._resolve_task_type(task, db)
        agent_id = self._registry.resolve_entrypoint(task_type)
        agent = self._registry.get_agent(agent_id)
        team_id = agent.team_id

        logger.info(
            "event=agent_route_resolved task_id=%s task_type=%s agent_id=%s team_id=%s",
            task.id,
            task_type,
            agent.agent_id,
            team_id or "none",
        )

        agent_input = self._build_input_contract(task, db, task_type, agent)
        logger.info(
            "event=agent_input_built task_id=%s agent_id=%s team_id=%s input_contract=%s output_contract=%s",
            task.id,
            agent.agent_id,
            team_id or "none",
            agent.input_contract.contract_id,
            agent.output_contract.contract_id,
        )

        handler = self._handlers.get(agent.handler_id)
        if handler is None:
            raise ValueError(f"unsupported agent handler_id: {agent.handler_id}")
        provider, model = self._executor_details(executor)
        logger.info(
            "event=ai_execution_started task_id=%s agent_id=%s team_id=%s provider=%s model=%s",
            task.id,
            agent.agent_id,
            team_id or "none",
            provider,
            model or "none",
        )
        execution = handler.execute(agent_input, executor)

        output = AgentOutputContract(
            task_id=task.id,
            task_type=task_type,
            agent_id=agent.agent_id,
            team_id=team_id,
            success=execution.success,
            result_text=execution.result_text,
            error_text=execution.error_text,
            metadata={
                "agent_output_contract_id": agent.output_contract.contract_id,
                "agent_output_contract_version": agent.output_contract.version,
                "provider": provider,
                "model": model,
            },
        )
        if output.success:
            logger.info(
                "event=ai_execution_completed task_id=%s agent_id=%s team_id=%s provider=%s model=%s",
                task.id,
                output.agent_id,
                output.team_id or "none",
                provider,
                model or "none",
            )
        else:
            logger.error(
                "event=ai_execution_failed task_id=%s agent_id=%s team_id=%s provider=%s model=%s error=%s",
                task.id,
                output.agent_id,
                output.team_id or "none",
                provider,
                model or "none",
                output.error_text or "unknown execution error",
            )
        logger.info(
            "event=agent_output_normalized task_id=%s agent_id=%s team_id=%s success=%s output_contract=%s",
            task.id,
            output.agent_id,
            output.team_id or "none",
            output.success,
            agent.output_contract.contract_id,
        )
        return output

    def _build_input_contract(self, task: Task, db: Session, task_type: str, agent: AgentDefinition) -> AgentInputContract:
        execution_input = prepare_task_execution_input(task, db)
        attachment_count = db.query(TaskAttachment).filter(TaskAttachment.task_id == task.id).count()
        return AgentInputContract(
            task_id=task.id,
            task_type=task_type,
            agent_id=agent.agent_id,
            team_id=agent.team_id,
            input_text=execution_input,
            metadata={
                "attachment_count": attachment_count,
                "agent_input_contract_id": agent.input_contract.contract_id,
                "agent_input_contract_version": agent.input_contract.version,
            },
        )

    @staticmethod
    def _resolve_task_type(task: Task, db: Session) -> str:
        has_attachments = db.query(TaskAttachment.id).filter(TaskAttachment.task_id == task.id).first() is not None
        if has_attachments:
            return "document_analysis"
        return "document_analysis"

    @staticmethod
    def _executor_details(executor: TaskExecutor) -> tuple[str, str | None]:
        provider = getattr(executor, "config", None)
        if provider is not None:
            return (
                str(getattr(provider, "provider", executor.__class__.__name__.lower())),
                getattr(provider, "model", None),
            )
        executor_name = executor.__class__.__name__.removesuffix("Executor").lower()
        return executor_name, None
