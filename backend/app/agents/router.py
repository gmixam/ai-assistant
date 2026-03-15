import json
import logging
from types import SimpleNamespace
from typing import Any, Protocol

from sqlalchemy.orm import Session

from ..attachment_pipeline import prepare_task_execution_input
from ..executors.base import ExecutionResult, TaskExecutor
from ..mail_attachment_service import build_email_attachment_analysis_text
from ..mail_providers.registry import MailProviderRegistry
from ..models import EmailAttachment, EmailSource, Task, TaskAttachment
from .models import (
    AgentDefinition,
    AgentInputContract,
    AgentOutputContract,
    AgentTeamDefinition,
    AgentTeamWorkflowStep,
    RouteResolution,
)
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


class EmailTriageTeamHandler:
    ACTION_PATTERNS: tuple[tuple[str, str], ...] = (
        ("approve", "approve_request"),
        ("review", "review_material"),
        ("reply", "send_reply"),
        ("respond", "send_reply"),
        ("pay", "process_payment"),
        ("payment", "process_payment"),
        ("sign", "sign_document"),
        ("schedule", "schedule_follow_up"),
        ("call", "schedule_follow_up"),
    )

    def __init__(
        self,
        registry: AgentRegistry,
        document_handler: DocumentAnalysisExecutionHandler,
        mail_provider_registry: MailProviderRegistry,
    ):
        self._registry = registry
        self._document_handler = document_handler
        self._mail_provider_registry = mail_provider_registry

    def execute(
        self,
        task: Task,
        db: Session,
        executor: TaskExecutor,
        team: AgentTeamDefinition,
    ) -> AgentOutputContract:
        email_source = (
            db.query(EmailSource)
            .filter(EmailSource.task_id == task.id)
            .order_by(EmailSource.id.desc())
            .first()
        )
        if email_source is None:
            raise ValueError(f"email source not found for email triage task {task.id}")
        email_attachments = (
            db.query(EmailAttachment)
            .filter(EmailAttachment.email_source_id == email_source.id)
            .order_by(EmailAttachment.id.asc())
            .all()
        )

        context: dict[str, Any] = {
            "task": task,
            "email_source": email_source,
            "email_attachments": email_attachments,
            "step_outputs": {},
        }

        final_agent_id = team.entry_agent_id
        final_result_text = None
        final_metadata: dict[str, Any] = {}

        for step in team.workflow_steps:
            if step.optional and step.agent_id == "attachment_analysis_agent" and not email_attachments:
                logger.info(
                    "event=team_step_skipped task_id=%s team_id=%s step_id=%s agent_id=%s reason=no_email_attachments",
                    task.id,
                    team.team_id,
                    step.step_id,
                    step.agent_id,
                )
                continue

            logger.info(
                "event=team_step_started task_id=%s team_id=%s step_id=%s agent_id=%s input_contract=%s output_contract=%s",
                task.id,
                team.team_id,
                step.step_id,
                step.agent_id,
                step.input_contract_id,
                step.output_contract_id,
            )
            step_output = self._execute_step(
                step,
                task,
                email_source,
                email_attachments,
                context,
                executor,
                team.team_id,
                db,
            )
            if not step_output.success:
                logger.error(
                    "event=team_step_failed task_id=%s team_id=%s step_id=%s agent_id=%s error=%s",
                    task.id,
                    team.team_id,
                    step.step_id,
                    step.agent_id,
                    step_output.error_text or "unknown team execution error",
                )
                return AgentOutputContract(
                    task_id=task.id,
                    task_type="email_triage",
                    agent_id=step.agent_id,
                    team_id=team.team_id,
                    success=False,
                    result_text=None,
                    error_text=step_output.error_text or "team step failed",
                    metadata={
                        "agent_output_contract_id": step.output_contract_id,
                        "agent_output_contract_version": "v1",
                    },
                )

            context["step_outputs"][step.agent_id] = step_output
            final_agent_id = step.agent_id
            final_result_text = step_output.result_text
            final_metadata = dict(step_output.metadata)

            logger.info(
                "event=team_step_completed task_id=%s team_id=%s step_id=%s agent_id=%s success=%s output_contract=%s",
                task.id,
                team.team_id,
                step.step_id,
                step.agent_id,
                step_output.success,
                step.output_contract_id,
            )
            if step.handoff_to is not None:
                next_agent = self._registry.get_agent(step.handoff_to)
                logger.info(
                    "event=agent_handoff task_id=%s team_id=%s from_agent_id=%s to_agent_id=%s output_contract=%s next_input_contract=%s",
                    task.id,
                    team.team_id,
                    step.agent_id,
                    next_agent.agent_id,
                    step.output_contract_id,
                    next_agent.input_contract.contract_id,
                )

        return AgentOutputContract(
            task_id=task.id,
            task_type="email_triage",
            agent_id=final_agent_id,
            team_id=team.team_id,
            success=True,
            result_text=final_result_text,
            error_text=None,
            metadata=final_metadata,
        )

    def _execute_step(
        self,
        step: AgentTeamWorkflowStep,
        task: Task,
        email_source: EmailSource,
        email_attachments: list[EmailAttachment],
        context: dict[str, Any],
        executor: TaskExecutor,
        team_id: str,
        db: Session,
    ) -> AgentOutputContract:
        if step.agent_id == "email_triage_agent":
            return self._execute_email_triage(task, email_source, email_attachments, team_id)
        if step.agent_id == "action_extraction_agent":
            return self._execute_action_extraction(task, email_source, context, team_id)
        if step.agent_id == "attachment_analysis_agent":
            return self._execute_attachment_analysis(task, email_source, email_attachments, executor, team_id, db)
        if step.agent_id == "approval_prep_agent":
            return self._execute_approval_prep(task, email_source, context, team_id)
        return AgentOutputContract(
            task_id=task.id,
            task_type="email_triage",
            agent_id=step.agent_id,
            team_id=team_id,
            success=False,
            error_text=f"unsupported team step agent_id: {step.agent_id}",
        )

    def _execute_email_triage(
        self,
        task: Task,
        email_source: EmailSource,
        email_attachments: list[EmailAttachment],
        team_id: str,
    ) -> AgentOutputContract:
        subject = (email_source.subject or "").strip()
        snippet = (email_source.snippet or "").strip()
        combined = f"{subject}\n{snippet}".lower()
        urgency = "low"
        if any(token in combined for token in ("urgent", "today", "asap", "deadline", "tomorrow")):
            urgency = "high"
        elif any(token in combined for token in ("review", "approve", "reply", "respond")):
            urgency = "medium"

        intent = "review_request"
        if any(token in combined for token in ("invoice", "payment", "pay")):
            intent = "payment_request"
        elif any(token in combined for token in ("contract", "agreement", "sign")):
            intent = "document_request"
        elif any(token in combined for token in ("reply", "respond")):
            intent = "response_request"

        reason_codes = json.loads(email_source.reason_codes_json or "[]")
        attachment_names = [attachment.filename or attachment.mime_type or f"attachment-{attachment.id}" for attachment in email_attachments]
        result_text = (
            f"Triage for email_source_id={email_source.id}: intent={intent}, urgency={urgency}, "
            f"attachments={len(email_attachments)}"
        )
        return AgentOutputContract(
            task_id=task.id,
            task_type="email_triage",
            agent_id="email_triage_agent",
            team_id=team_id,
            success=True,
            result_text=result_text,
            metadata={
                "triage_label": "deep_email",
                "intent": intent,
                "urgency": urgency,
                "reason_codes": reason_codes,
                "attachments_present": bool(email_attachments),
                "attachment_names": attachment_names,
                "sender": email_source.from_address,
                "subject": subject,
                "snippet": snippet,
            },
        )

    def _execute_action_extraction(
        self,
        task: Task,
        email_source: EmailSource,
        context: dict[str, Any],
        team_id: str,
    ) -> AgentOutputContract:
        triage = context["step_outputs"]["email_triage_agent"].metadata
        subject = (email_source.subject or "").strip()
        snippet = (email_source.snippet or "").strip()
        combined = f"{subject}\n{snippet}".lower()

        actions: list[str] = []
        for pattern, action_name in self.ACTION_PATTERNS:
            if pattern in combined and action_name not in actions:
                actions.append(action_name)
        if not actions:
            actions.append("review_email_request")

        deadlines: list[str] = []
        for marker in ("today", "tomorrow", "asap", "deadline", "this week"):
            if marker in combined:
                deadlines.append(marker)

        follow_ups = [
            f"Check sender {email_source.from_address}",
            "Confirm requested action before execution",
        ]
        result_text = f"Extracted actions: {', '.join(actions)}"
        return AgentOutputContract(
            task_id=task.id,
            task_type="email_triage",
            agent_id="action_extraction_agent",
            team_id=team_id,
            success=True,
            result_text=result_text,
            metadata={
                "actions": actions,
                "deadlines": deadlines,
                "follow_ups": follow_ups,
                "triage_intent": triage.get("intent"),
                "urgency": triage.get("urgency"),
            },
        )

    def _execute_attachment_analysis(
        self,
        task: Task,
        email_source: EmailSource,
        email_attachments: list[EmailAttachment],
        executor: TaskExecutor,
        team_id: str,
        db: Session,
    ) -> AgentOutputContract:
        attachment_analysis_input = build_email_attachment_analysis_text(
            email_source,
            email_attachments,
            self._mail_provider_registry,
            db,
        )
        agent_input = AgentInputContract(
            task_id=task.id,
            task_type="email_triage",
            agent_id="attachment_analysis_agent",
            team_id=team_id,
            input_text=(
                "Email attachment analysis via document-analysis bridge\n"
                f"email_source_id={email_source.id}\n"
                f"subject={email_source.subject or '(no subject)'}\n"
                "Downloaded attachment content:\n"
                + attachment_analysis_input
            ),
            metadata={
                "attachment_count": len(email_attachments),
                "bridge_capability": "document_analysis",
            },
        )
        logger.info(
            "event=attachment_analysis_reused task_id=%s team_id=%s agent_id=%s capability=document_analysis attachment_count=%s",
            task.id,
            team_id,
            "attachment_analysis_agent",
            len(email_attachments),
        )
        execution = self._document_handler.execute(agent_input, executor)
        return AgentOutputContract(
            task_id=task.id,
            task_type="email_triage",
            agent_id="attachment_analysis_agent",
            team_id=team_id,
            success=execution.success,
            result_text=execution.result_text,
            error_text=execution.error_text,
            metadata={
                "attachment_count": len(email_attachments),
                "analysis_mode": "document_analysis_bridge",
                "attachment_summary": [
                    f"- filename={attachment.filename or 'unknown'} mime_type={attachment.mime_type or 'unknown'} size={attachment.file_size or 0}"
                    for attachment in email_attachments
                ],
            },
        )

    def _execute_approval_prep(
        self,
        task: Task,
        email_source: EmailSource,
        context: dict[str, Any],
        team_id: str,
    ) -> AgentOutputContract:
        triage = context["step_outputs"]["email_triage_agent"].metadata
        actions = context["step_outputs"]["action_extraction_agent"].metadata
        attachment_step = context["step_outputs"].get("attachment_analysis_agent")
        attachment_result = attachment_step.result_text if attachment_step is not None else None
        primary_action = (actions.get("actions") or ["review_email_request"])[0]
        deadline_text = ", ".join(actions.get("deadlines") or []) or "none"
        summary = (
            f"Email from {email_source.from_address} requires approval. "
            f"Intent={triage.get('intent')}, urgency={triage.get('urgency')}, "
            f"subject={email_source.subject or '(no subject)'}."
        )
        proposed_action = primary_action
        structured_result = {
            "result_type": "approval_request",
            "action_type": primary_action,
            "team_id": team_id,
            "email_source_id": email_source.id,
            "provider": email_source.provider,
            "mailbox": email_source.mailbox,
            "sender": email_source.from_address,
            "subject": email_source.subject,
            "triage": triage,
            "actions": actions.get("actions") or [],
            "deadlines": actions.get("deadlines") or [],
            "follow_ups": actions.get("follow_ups") or [],
            "attachment_analysis": attachment_result,
        }
        handoff = (
            "await_human_approval: review extracted action, verify sender context, "
            f"confirm deadline={deadline_text}"
        )
        result_text = (
            f"Approval prepared for email_source_id={email_source.id}; "
            f"proposed_action={proposed_action}; handoff={handoff}"
        )
        return AgentOutputContract(
            task_id=task.id,
            task_type="email_triage",
            agent_id="approval_prep_agent",
            team_id=team_id,
            success=True,
            result_text=result_text,
            error_text=None,
            metadata={
                "approval_create_data": {
                    "summary": summary,
                    "proposed_action": proposed_action,
                    "structured_result": structured_result,
                    "handoff": handoff,
                },
                "suppress_task_delivery": True,
            },
        )


class ExecutionRouter:
    def __init__(self, registry: AgentRegistry, handlers: dict[str, ExecutionHandler] | None = None):
        self._registry = registry
        self._document_handler = DocumentAnalysisExecutionHandler()
        self._mail_provider_registry = MailProviderRegistry()
        self._email_team_handler = EmailTriageTeamHandler(
            registry,
            self._document_handler,
            self._mail_provider_registry,
        )
        self._handlers = handlers or {
            "legacy_document_analysis": self._document_handler,
            "attachment_document_analysis_bridge": self._document_handler,
            "email_triage_stub": StubExecutionHandler("email_triage_stub"),
            "action_extraction_stub": StubExecutionHandler("action_extraction_stub"),
            "approval_prep_stub": StubExecutionHandler("approval_prep_stub"),
        }

    def route(self, task: Task, db: Session, executor: TaskExecutor) -> AgentOutputContract:
        resolution = self.resolve(task, db)
        task_type = resolution.task_type
        agent = resolution.agent
        team_id = resolution.team.team_id if resolution.team is not None else agent.team_id

        logger.info(
            "event=agent_route_resolved task_id=%s task_type=%s agent_id=%s team_id=%s",
            task.id,
            task_type,
            agent.agent_id,
            team_id or "none",
        )

        if resolution.team is not None and resolution.team.team_id == "email_triage_team":
            output = self._route_email_team(task, executor, resolution, db)
            logger.info(
                "event=agent_output_normalized task_id=%s agent_id=%s team_id=%s success=%s output_contract=%s",
                task.id,
                output.agent_id,
                output.team_id or "none",
                output.success,
                self._registry.get_agent(output.agent_id).output_contract.contract_id,
            )
            return output

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

    def _route_email_team(
        self,
        task: Task,
        executor: TaskExecutor,
        resolution: RouteResolution,
        db: Session,
    ) -> AgentOutputContract:
        team = resolution.team
        if team is None:
            raise ValueError("email triage task requires team definition")
        entry_agent = resolution.agent
        logger.info(
            "event=agent_input_built task_id=%s agent_id=%s team_id=%s input_contract=%s output_contract=%s",
            task.id,
            entry_agent.agent_id,
            team.team_id,
            entry_agent.input_contract.contract_id,
            self._registry.get_agent("approval_prep_agent").output_contract.contract_id,
        )
        provider, model = self._executor_details(executor)
        logger.info(
            "event=ai_execution_started task_id=%s agent_id=%s team_id=%s provider=%s model=%s",
            task.id,
            entry_agent.agent_id,
            team.team_id,
            provider,
            model or "none",
        )
        output = self._email_team_handler.execute(task, db, executor, team)
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
        output.metadata.setdefault("provider", provider)
        output.metadata.setdefault("model", model)
        output.metadata.setdefault("agent_output_contract_id", self._registry.get_agent(output.agent_id).output_contract.contract_id)
        output.metadata.setdefault("agent_output_contract_version", self._registry.get_agent(output.agent_id).output_contract.version)
        return output

    def resolve(self, task: Task, db: Session) -> RouteResolution:
        task_type = self._resolve_task_type(task, db)
        agent_id = self._registry.resolve_entrypoint(task_type)
        agent = self._registry.get_agent(agent_id)
        team = self._registry.get_team(agent.team_id) if agent.team_id else None
        return RouteResolution(task_type=task_type, agent=agent, team=team)

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
        email_source = db.query(EmailSource.id).filter(EmailSource.task_id == task.id).first()
        if email_source is not None:
            return "email_triage"
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
