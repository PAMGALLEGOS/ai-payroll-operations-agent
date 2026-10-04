"""Streamlit interface (CP4, spec §13): Validation Dashboard + Chat.

    streamlit run app/web/streamlit_app.py

The UI only talks to the API over HTTP (D10). It never imports the Agent, the
Engine or an LLM, and it never calculates a validation outcome: counts come from
the Engine summary, and the tables in the chat come from `validation.results`,
never from the answer text.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repository root

import streamlit as st  # noqa: E402

from app.web import api_client, views  # noqa: E402
from app.web.i18n import DEFAULT_LANGUAGE, EXAMPLE_QUESTIONS, t  # noqa: E402

st.set_page_config(page_title="Payroll Validation Agent", page_icon="🧾", layout="wide")

# ------------------------------------------------------------------ state
defaults = {"lang": DEFAULT_LANGUAGE, "view": "dashboard", "messages": [], "session_id": None,
            "queued": None, "show_details": True}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)

client = api_client.make_client()


def queue_question(question: str) -> None:
    st.session_state.queued = question
    st.session_state.view = "chat"


def new_conversation() -> None:
    st.session_state.messages = []
    st.session_state.session_id = None


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.session_state.lang = st.radio(
        t("language", st.session_state.lang), ["es", "en"],
        index=["es", "en"].index(st.session_state.lang),
        format_func=lambda code: {"es": "Español", "en": "English"}[code], horizontal=True,
    )
    lang = st.session_state.lang

    st.session_state.view = st.radio(
        "view", ["dashboard", "chat"], index=["dashboard", "chat"].index(st.session_state.view),
        format_func=lambda v: t("tab_dashboard" if v == "dashboard" else "tab_chat", lang),
        label_visibility="collapsed",
    )

    st.subheader(t("api_status", lang))
    try:
        health = client.health()
        ok = health["status"] == "ok"
        st.markdown(f"{'🟢' if ok else '🟠'} **{t('status_ok' if ok else 'status_degraded', lang)}**")
        for label, status in views.health_rows(health, lang):
            st.caption(f"{label}: {status}")
    except api_client.ApiUnavailable:
        st.error(t("api_down", lang))

    st.subheader(t("examples", lang))
    for question in EXAMPLE_QUESTIONS[lang]:
        st.button(question, key=f"ex-{lang}-{question}", on_click=queue_question, args=(question,),
                  use_container_width=True)

    st.divider()
    st.session_state.show_details = st.toggle(t("show_details", lang), value=st.session_state.show_details)
    st.button(t("new_conversation", lang), on_click=new_conversation, use_container_width=True)

st.title(t("app_title", lang))
st.caption(t("app_subtitle", lang))


# -------------------------------------------------------------- dashboard
def render_dashboard() -> None:
    st.info(t("dashboard_note", lang))
    try:
        everything = client.validation()
    except api_client.ApiUnavailable:
        st.error(t("api_down", lang))
        return
    except api_client.ApiResponseError as error:
        st.error(f"{t('error_prefix', lang)}: {error.message} ({error.trace_id})")
        return

    st.caption(views.run_caption(everything["run"], lang))
    st.subheader(t("filters", lang))
    c1, c2, c3 = st.columns(3)
    all_label = t("all", lang)
    employee = c1.selectbox(t("filter_employee", lang), [all_label] + views.employee_options(everything["results"]))
    vtype = c2.selectbox(t("filter_type", lang), [all_label, "gross_pay", "total_deductions", "net_pay"])
    status = c3.selectbox(t("filter_status", lang), [all_label, "PASS", "FAIL"])

    filters = {
        "period": everything["period"],
        "employee_id": None if employee == all_label else employee,
        "validation_type": None if vtype == all_label else vtype,
        "status": None if status == all_label else status,
    }
    data = everything if all(v is None for k, v in filters.items() if k != "period") else client.validation(**filters)

    columns = st.columns(5)
    for column, (label, value) in zip(columns, views.summary_metrics(data["summary"], lang)):
        column.metric(label, value)

    left, right = st.columns([3, 1])
    with left:
        st.subheader(t("results_table", lang))
        if data["results"]:
            st.dataframe(views.results_rows(data["results"], lang), hide_index=True, use_container_width=True)
        else:
            st.write(t("no_results", lang))
    with right:
        st.subheader(t("reason_chart", lang))
        counts = views.reason_code_counts(data["summary"])
        if counts:
            st.bar_chart(counts, horizontal=True)
        else:
            st.write(t("no_exceptions", lang))


# ------------------------------------------------------------------- chat
def render_response(response: dict) -> None:
    label, color = views.route_badge(response["route"], lang)
    st.badge(label, color=color)
    if views.llm_degraded(response):
        st.warning(t("llm_degraded", lang), icon="⚠️")
    st.markdown(response["answer"].replace("\n", "  \n"))

    validation = response.get("validation") or {}
    if validation.get("results"):
        st.caption(t("engine_facts", lang))
        st.dataframe(views.results_rows(validation["results"], lang), hide_index=True, use_container_width=True)
    if response.get("evidence"):
        with st.expander(t("sources", lang)):
            st.dataframe(views.source_rows(response["evidence"], lang), hide_index=True, use_container_width=True)
    if response.get("human_in_the_loop"):
        st.info(response["human_in_the_loop"], icon="🧑‍⚖️")
    if st.session_state.show_details:
        with st.expander(t("technical_details", lang)):
            st.json(views.technical_details(response))


def render_chat() -> None:
    st.caption(t("chat_intro", lang))
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            elif "response" in message:
                render_response(message["response"])
            else:
                st.error(message["content"])

    typed = st.chat_input(t("chat_placeholder", lang))
    question = typed or st.session_state.queued
    st.session_state.queued = None
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner(t("thinking", lang)):
                response = client.chat(question, st.session_state.session_id)
        except api_client.ApiUnavailable:
            st.session_state.messages.append({"role": "assistant", "content": t("api_down", lang)})
            st.error(t("api_down", lang))
            return
        except api_client.ApiResponseError as error:
            text = f"{t('error_prefix', lang)}: {error.message} ({error.trace_id})"
            st.session_state.messages.append({"role": "assistant", "content": text})
            st.error(text)
            return
        st.session_state.session_id = response["session_id"]
        st.session_state.messages.append({"role": "assistant", "response": response})
        render_response(response)


if st.session_state.view == "dashboard":
    render_dashboard()
else:
    render_chat()
