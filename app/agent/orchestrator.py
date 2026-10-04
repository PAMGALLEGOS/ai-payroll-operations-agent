"""The Agent: Understand -> Decide -> Obtain -> Respond.

    1. Understand  language, entities (deterministic), intent (LLM, keyword fallback)
    2. Decide      deterministic rules first (prohibited action, pending clarification,
                   several employees), then the routing matrix
    3. Obtain      Validation Tool (read-only run file) and / or Retriever (guarded by N9)
    4. Respond     Engine facts by template; LLM only for explanations;
                   Auditor ALLOW / REVISE (one rewrite) / BLOCK

Every failure degrades towards fewer generated words and more deterministic
facts, never towards an invented answer.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agent import prompts
from app.agent import responses as R
from app.agent.contracts import AgentRequest, AgentResponse
from app.agent.entities import Entities, extract_entities, remainder_without_entities
from app.agent.explainer import Explainer
from app.agent.intent import IntentClassifier, IntentDecision
from app.agent.keywords import is_prohibited_action, mentions_legal_or_real_country
from app.agent.knowledge_guard import KnowledgeGuard
from app.agent.language import detect_language
from app.agent.router import RouteDecision, decide_route, needs_employee
from app.agent.session import PendingQuestion, SessionState, SessionStore
from app.audit.auditor import Auditor, AuditReport
from app.audit.checks import AuditContext
from app.llm.client import LLMClient, LLMError
from app.observability.context import current_trace_id, new_trace_id, reset_trace_id, set_trace_id
from app.observability.events import AgentObserver, NullObserver, message_fingerprint
from app.rag.retriever import Retriever
from app.validation.tool import ToolError, ToolResult, ValidationTool

MAX_PENDING_REMAINDER_WORDS = 3


@dataclass
class Turn:
    """Everything known about the message being answered."""

    trace_id: str
    message: str
    language: str
    entities: Entities
    session: SessionState
    intent: str | None = None
    retrieval_query: str = ""
    route_source: str = "llm_intent"
    employee_id: str | None = None
    period: str | None = None
    validation_types: list[str] | None = None
    sources: dict[str, str] = field(default_factory=dict)
    prompts_used: list[str] = field(default_factory=list)
    llm_degraded: list[str] = field(default_factory=list)   # LLM tasks that failed and fell back (F2)


class Agent:
    def __init__(
        self,
        tool: ValidationTool,
        llm: LLMClient,
        retriever: Retriever | None,
        knowledge_guard: KnowledgeGuard,
        sessions: SessionStore | None = None,
        auditor: Auditor | None = None,
        clock: Callable[[], float] = time.perf_counter,
        observer: AgentObserver | None = None,
    ):
        self.tool = tool
        self.llm = llm
        self.retriever = retriever
        self.guard = knowledge_guard
        self.sessions = sessions or SessionStore()
        self.auditor = auditor or Auditor()
        self.classifier = IntentClassifier(llm)
        self.explainer = Explainer(llm)
        self.clock = clock
        # Observability hooks (D4-08): they only report, they never change a decision.
        self.observer: AgentObserver = observer or NullObserver()
        self._retrieval_lock = threading.Lock()

    def replace_retriever(self, retriever: Retriever | None, guard: KnowledgeGuard) -> None:
        """Swap the knowledge index after a re-ingestion, without a restart (D4-07)."""
        with self._retrieval_lock:
            self.retriever, self.guard = retriever, guard

    # ================================================================ entry
    def handle(self, request: AgentRequest) -> AgentResponse:
        started = self.clock()
        # Reuse the trace_id of the surrounding API request when there is one (CP4), so the
        # api_request event and the Agent events share one id; otherwise create a new one.
        trace_id = current_trace_id() or new_trace_id()
        token = set_trace_id(trace_id)
        try:
            with self.sessions.lock(request.session_id):
                session = self.sessions.get(request.session_id)
                message = (request.message or "").strip()[:1000]
                turn = Turn(
                    trace_id=trace_id,
                    message=message,
                    language=detect_language(message, default=session.language),  # type: ignore[arg-type]
                    entities=extract_entities(message),
                    session=session,
                )
                self.observer.emit("request_received", language=turn.language, message_length=len(message),
                                   message_hash=message_fingerprint(message))
                try:
                    response = self._answer(turn)
                except Exception as error:  # last line of defence: never leak internals, never invent
                    self.observer.emit("error", component="agent", error_type=type(error).__name__)
                    response = self._response(turn, "CLARIFY", R.t("safe_error", turn.language, trace_id=trace_id),
                                              "safe_fallback", route_source="error")
                self._remember(turn, response)
            # F2: which LLM tasks failed and were replaced by deterministic fallbacks.
            response.versions["llm_degraded"] = list(turn.llm_degraded)
            response.latency_ms = int((self.clock() - started) * 1000)
            self.observer.emit("route_decided", route=response.route, intent=response.intent,
                               route_source=response.route_source)
            self.observer.emit("response_completed", route=response.route, answer_mode=response.answer_mode,
                               evidence_status=response.evidence_status, verdict=response.audit.get("verdict"),
                               revised=response.audit.get("revised", False), latency_ms=response.latency_ms)
            return response
        finally:
            reset_trace_id(token)

    # ============================================================ decide
    def _answer(self, turn: Turn) -> AgentResponse:
        if not any(ch.isalnum() for ch in turn.message):
            return self._clarify(turn, "empty_message", route_source="rule")

        pending = self._resume_pending(turn)
        if pending is None:
            turn.session.pending = None
            if is_prohibited_action(turn.message):
                return self._out_of_scope(turn, "prohibited_action", route_source="rule")
            decision: IntentDecision = self.classifier.classify(turn.message, turn.entities, turn.session)
            turn.intent, turn.retrieval_query, turn.route_source = (
                decision.intent, decision.retrieval_query, decision.source)
            turn.prompts_used.append(prompts.INTENT)
            self.observer.emit("intent_identified", intent=decision.intent, source=decision.source)
            if decision.source == "fallback":
                self._degraded(turn, "intent")
            if len(turn.entities.employee_ids) > 1:
                return self._clarify(turn, "multiple_employees", route_source="rule")

        self._resolve_entities(turn)
        route = decide_route(
            turn.intent or "unclear",
            employee_id=turn.employee_id,
            period=turn.period,
            legal_reference=mentions_legal_or_real_country(turn.message),
        )
        return self._dispatch(turn, route)

    def _resume_pending(self, turn: Turn) -> PendingQuestion | None:
        """Complete a question that was waiting for an employee id or a period."""
        pending = turn.session.pending
        if pending is None:
            return None
        short_reply = len(remainder_without_entities(turn.message).split()) <= MAX_PENDING_REMAINDER_WORDS
        filled = (
            (pending.missing == "employee_id" and len(turn.entities.employee_ids) == 1)
            or (pending.missing == "period" and turn.entities.period is not None)
        )
        if not (short_reply and filled):
            return None
        turn.intent = pending.intent
        turn.route_source = "pending_clarification"
        turn.entities = Entities(
            employee_ids=turn.entities.employee_ids or ([pending.employee_id] if pending.employee_id else []),
            period=turn.entities.period or pending.period,
            validation_type=turn.entities.validation_type or pending.validation_type,
            status_filter=turn.entities.status_filter,
        )
        turn.session.pending = None
        return pending

    def _resolve_entities(self, turn: Turn) -> None:
        ents, session = turn.entities, turn.session
        intent = turn.intent or "unclear"

        if ents.employee_id:
            turn.employee_id, turn.sources["employee_id"] = ents.employee_id, "message"
        elif needs_employee(intent) and session.employee_id:
            turn.employee_id, turn.sources["employee_id"] = session.employee_id, "session"

        if ents.period:
            turn.period, turn.sources["period"] = ents.period, "message"
        elif session.period:
            turn.period, turn.sources["period"] = session.period, "session"
        else:
            periods = self.tool.available_periods()
            if len(periods) == 1:  # decision C3-05
                turn.period, turn.sources["period"] = periods[0], "default_single_run"

        if ents.validation_type:
            turn.validation_types, turn.sources["validation_type"] = [ents.validation_type], "message"
        elif (turn.sources.get("employee_id") == "session" and intent == "validation_lookup"
              and session.validation_focus):
            turn.validation_types, turn.sources["validation_type"] = list(session.validation_focus), "session_focus"

    def _dispatch(self, turn: Turn, route: RouteDecision) -> AgentResponse:
        if route.route == "CLARIFY":
            return self._clarify(turn, route.reason or "unclear_intent", missing=route.missing)
        if route.route == "OUT_OF_SCOPE":
            return self._out_of_scope(turn, route.reason or "off_topic")
        if route.route == "RAG":
            return self._rag(turn)
        if route.route == "TOOL":
            return self._tool(turn)
        return self._tool_rag(turn)

    # ============================================================ routes
    def _clarify(self, turn: Turn, reason: str, *, missing: str | None = None,
                 route_source: str | None = None) -> AgentResponse:
        lang = turn.language
        if reason == "missing_employee":
            text = R.t("clarify_missing_employee", lang)
        elif reason == "missing_period":
            periods = self.tool.available_periods()
            text = (R.t("clarify_missing_period", lang, periods=", ".join(periods)) if periods
                    else R.t("clarify_no_periods", lang))
        elif reason == "multiple_employees":
            joiner = " o " if lang == "es" else " or "
            text = R.t("clarify_multiple_employees", lang, list=joiner.join(turn.entities.employee_ids))
            missing = "employee_id"
        else:
            text = R.t("clarify_unclear", lang)

        if missing and turn.intent:
            turn.session.pending = PendingQuestion(
                intent=turn.intent, missing=missing, original_message=turn.message,
                validation_type=turn.entities.validation_type, period=turn.period,
                employee_id=turn.employee_id if missing != "employee_id" else None,
            )
        response = self._response(turn, "CLARIFY", text, "template", route_source=route_source)
        response.clarification = {"reason": reason, "missing": missing}
        return self._audit_template(response, turn)

    def _out_of_scope(self, turn: Turn, reason: str, *, route_source: str | None = None) -> AgentResponse:
        response = self._response(turn, "OUT_OF_SCOPE", R.t(f"oos_{reason}", turn.language), "template",
                                  route_source=route_source)
        response.out_of_scope = {"reason": reason}
        if reason == "prohibited_action":
            response.human_in_the_loop = R.t("hitl", turn.language)
        return self._audit_template(response, turn)

    def _query_tool(self, turn: Turn, **filters: Any) -> tuple[ToolResult | None, str | None]:
        self.observer.emit("tool_called", period=turn.period,
                           filters={k: v for k, v in filters.items() if v is not None})
        try:
            result = self.tool.query(turn.period, **filters)  # type: ignore[arg-type]
        except ToolError as error:
            key = "no_run" if "No validation run" in str(error) else "run_untrusted"
            self.observer.emit("tool_error", error_type=key)
            return None, R.t(key, turn.language, period=turn.period)
        self.observer.emit("engine_result", found=result.found, results=len(result.results),
                           fail_count=result.summary["fail_count"], run_id=result.run.get("run_id"))
        return result, None

    def _tool(self, turn: Turn) -> AgentResponse:
        lang = turn.language
        if turn.intent == "aggregate_lookup":
            result, error = self._query_tool(
                turn,
                employee_id=turn.entities.employee_id,   # only an employee named in THIS message
                validation_type=turn.entities.validation_type,
            )
            if result is None:
                return self._audit_template(self._response(turn, "TOOL", error or "", "template"), turn)
            list_failures = turn.entities.status_filter == "FAIL"
            text = R.aggregate_facts(result, lang, list_failures) if result.found else R.no_match(result, lang)
        else:
            result, error = self._query_tool(turn, employee_id=turn.employee_id)
            if result is None:
                return self._audit_template(self._response(turn, "TOOL", error or "", "template"), turn)
            if result.found:
                shown = turn.validation_types if turn.validation_types else None
                text = R.employee_facts(result, turn.employee_id or "", lang, only_types=shown)
            else:
                text = R.no_match(result, lang)

        response = self._response(turn, "TOOL", text, "template", tool_result=result)
        if result.found and result.summary["fail_count"]:
            response.human_in_the_loop = R.t("hitl", lang)
        return self._audit_template(response, turn, tool_result=result)

    def _tool_rag(self, turn: Turn) -> AgentResponse:
        lang = turn.language
        readiness = turn.intent == "readiness_question"
        result, error = self._query_tool(turn) if readiness else self._query_tool(turn, employee_id=turn.employee_id)
        if result is None:
            return self._audit_template(self._response(turn, "TOOL_RAG", error or "", "template"), turn)
        if not result.found:
            return self._audit_template(
                self._response(turn, "TOOL_RAG", R.no_match(result, lang), "template", tool_result=result), turn)

        facts_text = R.readiness_facts(result, lang) if readiness else R.employee_facts(
            result, turn.employee_id or "", lang)
        facts_payload = ({"summary": result.summary, "run": result.run} if readiness
                         else {"results": result.results, "run": result.run})
        query = _retrieval_query_for(result, readiness)

        response = self._response(turn, "TOOL_RAG", facts_text, "template", tool_result=result)
        response.human_in_the_loop = R.t("hitl", lang)
        evidence, status = self._retrieve(query)
        response.evidence_status = status
        if status != "sufficient":
            note = R.t("rag_blocked" if status in ("blocked_stale_index", "unavailable") else "explanation_unavailable", lang)
            response.answer = f"{facts_text}\n\n{note}"
            return self._audit_template(response, turn, tool_result=result)

        response.evidence = [_evidence_meta(e) for e in evidence]
        turn.prompts_used.append(prompts.TOOL_RAG_EXPLAIN)
        ctx = self._audit_context(turn, "TOOL_RAG", result, evidence, requires_citation=True)
        explanation, report, revised = self._generate_audited(
            lambda issues: self.explainer.explain_results(turn.message, facts_payload, evidence, lang, issues), ctx,
            turn=turn, task="tool_rag_explain")

        if explanation is None:
            fallback = R.t("blocked", lang) if report else R.t("explanation_unavailable", lang)
            response.answer = f"{facts_text}\n\n{fallback}\n{R.sources_list(response.evidence, lang)}"
            response.answer_mode = "safe_fallback" if report else "template"
        else:
            response.answer = f"{facts_text}\n\n{R.t('why', lang)} {explanation}"
            response.answer_mode = "template+llm"
        response.audit = _audit_dict(report, revised) if report else self._template_audit(response, turn, result)
        return response

    def _rag(self, turn: Turn) -> AgentResponse:
        lang = turn.language
        query = turn.retrieval_query or turn.message
        evidence, status = self._retrieve(query)
        response = self._response(turn, "RAG", "", "template")
        response.evidence_status = status
        if status in ("blocked_stale_index", "unavailable"):
            response.answer = R.t("rag_blocked", lang)
            return self._audit_template(response, turn)
        if status == "insufficient":
            response.answer = R.t("rag_insufficient", lang)
            return self._audit_template(response, turn)

        response.evidence = [_evidence_meta(e) for e in evidence]
        turn.prompts_used.append(prompts.RAG_ANSWER)
        ctx = self._audit_context(turn, "RAG", None, evidence, requires_citation=True)
        answer, report, revised = self._generate_audited(
            lambda issues: self.explainer.answer_from_documents(turn.message, evidence, lang, issues), ctx,
            turn=turn, task="rag_answer")

        if answer is None:
            prefix = R.t("blocked", lang) if report else R.t("explanation_unavailable", lang)
            response.answer = f"{prefix}\n{R.sources_list(response.evidence, lang)}"
            response.answer_mode = "safe_fallback"
            response.audit = _audit_dict(report, revised) if report else self._template_audit(response, turn, None)
        else:
            response.answer = answer
            response.answer_mode = "llm"
            response.audit = _audit_dict(report, revised)
        return response

    # ============================================================ helpers
    def _retrieve(self, query: str) -> tuple[list[dict[str, Any]], str]:
        with self._retrieval_lock:          # a consistent (retriever, guard) pair during re-ingestion
            retriever, guard = self.retriever, self.guard
        status = guard.status()
        if status == "stale":
            evidence, outcome, top = [], "blocked_stale_index", None
        elif status == "missing" or retriever is None:
            evidence, outcome, top = [], "unavailable", None
        else:
            result = retriever.search(query)
            top = round(result.top_score, 4)
            if result.sufficient_evidence:
                evidence, outcome = [r.to_dict() for r in result.results], "sufficient"
            else:
                evidence, outcome = [], "insufficient"
        self.observer.emit("rag_retrieved", evidence_status=outcome, chunks=len(evidence), top_score=top)
        return evidence, outcome

    def _degraded(self, turn: Turn, task: str) -> None:
        turn.llm_degraded.append(task)
        self.observer.emit("llm_fallback", task=task)

    def _generate_audited(self, generate: Callable[[list[str] | None], str], ctx: AuditContext, *,
                          turn: Turn, task: str) -> tuple[str | None, AuditReport | None, bool]:
        """Generate, audit, rewrite once if needed (D9). Returns (text or None, last report, revised)."""
        try:
            text = generate(None)
        except LLMError:
            self._degraded(turn, task)
            return None, None, False
        report = self.auditor.review(text, ctx)
        self._emit_audit(report, 1)
        if report.verdict == "ALLOW":
            return text, report, False
        if report.verdict == "BLOCK":
            return None, report, False
        try:
            rewritten = generate(report.feedback())
        except LLMError:
            self._degraded(turn, task)
            return None, report, True
        second = self.auditor.review(rewritten, ctx, is_rewrite=True)
        self._emit_audit(second, 2)
        return (rewritten if second.verdict == "ALLOW" else None), second, True

    def _audit_context(self, turn: Turn, route: str, result: ToolResult | None,
                       evidence: list[dict[str, Any]], requires_citation: bool = False) -> AuditContext:
        allowed = set(turn.entities.employee_ids)
        if turn.employee_id:
            allowed.add(turn.employee_id)
        if result is not None:
            allowed.update(r["employee_id"] for r in result.results)
            allowed.update(result.summary.get("employees_with_exceptions", []))
        return AuditContext(
            route=route, language=turn.language, question=turn.message,
            facts=result.results if result else [],
            summary=result.summary if result else None,
            chunks=[{"chunk_id": e["chunk_id"], "content": e["content"]} for e in evidence],
            allowed_employee_ids=allowed, requires_citation=requires_citation,
        )

    def _template_audit(self, response: AgentResponse, turn: Turn, result: ToolResult | None) -> dict[str, Any]:
        ctx = self._audit_context(turn, response.route, result, [])
        ctx.chunks = [{"chunk_id": e["chunk_id"], "content": ""} for e in response.evidence]
        report = self.auditor.review(response.answer, ctx)
        self._emit_audit(report, "template")
        return _audit_dict(report, False)

    def _emit_audit(self, report: AuditReport, attempt: int | str) -> None:
        self.observer.emit("auditor_result", attempt=attempt, verdict=report.verdict,
                           failed_checks=[c.name for c in report.failed])

    def _audit_template(self, response: AgentResponse, turn: Turn,
                        tool_result: ToolResult | None = None) -> AgentResponse:
        response.audit = self._template_audit(response, turn, tool_result)
        return response

    def _response(self, turn: Turn, route: str, answer: str, mode: str, *,
                  route_source: str | None = None, tool_result: ToolResult | None = None) -> AgentResponse:
        validation = None
        if tool_result is not None:
            validation = {"run": tool_result.run, "filters": tool_result.filters,
                          "found": tool_result.found, "results": tool_result.results,
                          "summary": tool_result.summary}
        return AgentResponse(
            trace_id=turn.trace_id,
            session_id=turn.session.session_id,
            language=turn.language,
            route=route,  # type: ignore[arg-type]
            route_source=route_source or turn.route_source,
            intent=turn.intent,
            entities={"employee_id": turn.employee_id, "period": turn.period,
                      "validation_types": turn.validation_types,
                      "employee_ids_in_message": turn.entities.employee_ids},
            entities_source=dict(turn.sources),
            answer=answer,
            answer_mode=mode,  # type: ignore[arg-type]
            validation=validation,
            versions={
                "prompts": list(turn.prompts_used),
                "llm": f"{self.llm.name}/{self.llm.model}",
                "embeddings": (f"{self.retriever.provider.name}/{self.retriever.provider.model}"
                               if self.retriever else None),
                "engine_version": tool_result.run.get("engine_version") if tool_result else None,
                "rules_version": tool_result.run.get("rules_version") if tool_result else None,
            },
        )

    def _remember(self, turn: Turn, response: AgentResponse) -> None:
        session = turn.session
        session.language = turn.language
        if response.route in ("TOOL", "TOOL_RAG") and response.validation and response.validation["found"]:
            if turn.employee_id and turn.intent in ("validation_lookup", "validation_explanation"):
                if turn.employee_id != session.employee_id:
                    session.validation_focus = []
                session.employee_id = turn.employee_id
                failed = [r["validation_type"] for r in response.validation["results"] if r["status"] == "FAIL"]
                if failed:
                    session.validation_focus = failed
            session.period = turn.period
        if response.route != "CLARIFY":
            session.last_intent = turn.intent
        session.last_route = response.route
        session.record_turn(turn.message, response.route, turn.intent, response.entities)
        self.sessions.touch(session)


# ================================================================ helpers
def _audit_dict(report: AuditReport | None, revised: bool) -> dict[str, Any]:
    if report is None:
        return {}
    return {"verdict": report.verdict, "revised": revised, "checks": [c.to_dict() for c in report.checks]}


def _evidence_meta(e: dict[str, Any]) -> dict[str, Any]:
    meta = e["metadata"]
    return {"chunk_id": e["chunk_id"], "score": e["score"], "source_document": meta["source_document"],
            "document_title": meta["document_title"], "section": meta["section"], "content": e["content"]}


def _retrieval_query_for(result: ToolResult, readiness: bool) -> str:
    """Retrieval query built by code from the Engine outcome, never from the LLM.

    Written as natural English questions (like the questions the Gemini threshold
    was calibrated on), because the knowledge base is in English whatever the
    language of the conversation.
    """
    if readiness:
        return "What are the prerequisites before the approver can approve a payroll period?"
    questions: list[str] = []
    for r in result.results:
        if r["status"] == "PASS":
            continue
        vtype = r["validation_type"].replace("_", " ")
        if r["reason_code"] == "OUT_OF_TOLERANCE":
            questions.append(f"What is the {vtype} tolerance and how is an OUT_OF_TOLERANCE exception reviewed?")
        elif r["reason_code"] == "MISSING_INPUT":
            questions.append(f"What happens when an input value is missing for {vtype} (MISSING_INPUT)?")
        else:
            questions.append(f"When is an input value invalid for {vtype} (INVALID_INPUT), such as a negative value?")
    if not questions:
        types = ", ".join(sorted({r["validation_type"].replace("_", " ") for r in result.results}))
        return f"When does a {types} validation PASS within its tolerance?"
    return " ".join(dict.fromkeys(questions))
