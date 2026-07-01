import os
import re
import json
import logging
from typing import AsyncGenerator
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioServerParameters
from google.adk.workflow import Workflow, node, JoinNode, START
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types

from app.config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studybuddy")

# Define MCP server connection
mcp_tools = McpToolset(
    connection_params=StdioServerParameters(
        command="uv",
        args=["run", "app/mcp_server.py"]
    )
)

# Define sub-agents
study_scheduler_agent = LlmAgent(
    name="study_scheduler_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a specialized study scheduler. Your job is to create optimized weekly study blocks. "
        "Use the MCP tools to query existing calendar events (get_calendar_events) and add scheduled study blocks (add_study_block). "
        "Ensure study hours are balanced and do not overlap with existing exams or deadlines."
    ),
    tools=[mcp_tools],
)

exam_prep_agent = LlmAgent(
    name="exam_prep_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a specialized exam prep planner. Your job is to design milestone-based study timelines leading up to exam dates. "
        "Use the MCP tools to calculate the countdown (calculate_countdown) and retrieve specific study tips (get_study_tips) for subjects. "
        "Provide actionable advice and spaced reviews."
    ),
    tools=[mcp_tools],
)

# Output schema for Orchestrator Agent
class StudyPlan(BaseModel):
    scheduler_summary: str = Field(description="A summary of the weekly study blocks and schedule.")
    prep_summary: str = Field(description="A summary of the exam prep milestones and timelines.")
    final_itinerary: str = Field(description="A detailed day-by-day or week-by-week study itinerary.")

# Define Orchestrator
orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the StudyBuddy Orchestrator. Coordinate with study_scheduler_agent to build weekly study blocks, "
        "and with exam_prep_agent to design milestones for upcoming exams. Synthesize their outputs into a unified StudyPlan. "
        "If the input contains user feedback or requested adjustments, modify the plan to address those adjustments. "
        "YOU MUST ALWAYS RESPOND WITH A VALID JSON OBJECT conforming to the StudyPlan schema, even if the user's request is off-topic, a greeting, or invalid. "
        "If the request is off-topic, a greeting, or invalid, fill all the schema fields with a polite notice explaining that you can only assist with academic scheduling and exam planning. "
        "Do not output any plain conversational text outside the JSON structure under any circumstances."
    ),
    tools=[AgentTool(study_scheduler_agent), AgentTool(exam_prep_agent)],
    output_schema=StudyPlan,
    output_key="study_plan",
)

# Node 1: Security Checkpoint
def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Checks for prompt injections, scrubs PII, and validates domain rules."""
    input_text = ""
    if hasattr(node_input, "parts") and node_input.parts:
        input_text = " ".join([p.text for p in node_input.parts if p.text])
    elif isinstance(node_input, str):
        input_text = node_input
    
    # Check for prompt injection keywords
    injection_keywords = ["ignore instructions", "system prompt", "bypass", "jailbreak", "override instructions", "you are now a"]
    detected_injection = any(kw in input_text.lower() for kw in injection_keywords)
    
    if detected_injection:
        audit_log = {
            "event": "security_check",
            "severity": "CRITICAL",
            "reason": "Prompt injection detected",
            "input_preview": input_text[:50]
        }
        logger.warning(json.dumps(audit_log))
        return Event(
            route="security_event", 
            state={"security_alert": True, "error_msg": "Access Denied: Security Check Failed due to potential prompt injection."}
        )
    
    # PII Scrubbing: Regex for emails, phone numbers, and Student IDs (S12345)
    scrubbed_text = input_text
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
    student_id_pattern = r'\bS\d{5,8}\b'
    
    scrubbed_text = re.sub(email_pattern, "[EMAIL_REDACTED]", scrubbed_text)
    scrubbed_text = re.sub(phone_pattern, "[PHONE_REDACTED]", scrubbed_text)
    scrubbed_text = re.sub(student_id_pattern, "[STUDENT_ID_REDACTED]", scrubbed_text)
    
    # Domain specific rule: check if user asks to schedule too many hours
    excessive_study = False
    hours_match = re.search(r'(\d+)\s*hours', scrubbed_text, re.IGNORECASE)
    if hours_match:
        hours = int(hours_match.group(1))
        if hours > 16:
            excessive_study = True
            
    if excessive_study:
        audit_log = {
            "event": "security_check",
            "severity": "WARNING",
            "reason": "Excessive study hours requested (>16h)",
            "input_preview": scrubbed_text[:50]
        }
        logger.info(json.dumps(audit_log))
        return Event(
            route="security_event",
            state={"security_alert": True, "error_msg": "Safety Advisory: Please request a balanced schedule with less than 16 hours of daily study."}
        )
    
    # All checks passed
    audit_log = {
        "event": "security_check",
        "severity": "INFO",
        "reason": "All safety checks passed",
        "input_preview": scrubbed_text[:50]
    }
    logger.info(json.dumps(audit_log))
    
    return Event(
        route="safe",
        output=scrubbed_text,
        state={"clean_input": scrubbed_text}
    )

# Node 2: Security Event Node
def security_event_node(ctx: Context) -> Event:
    """Handles safety violations by displaying a message to the user."""
    error_msg = ctx.state.get("error_msg", "Security validation failed.")
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=f"⚠️ Security Alert: {error_msg}")]
        )
    )
    yield Event(output={"status": "rejected", "message": error_msg})

# Node 4: HITL Review Node
async def hitl_review_node(ctx: Context, node_input: dict) -> AsyncGenerator[Event, None]:
    """Provides a Human-in-the-loop review step for the generated Study Plan."""
    # If the user has not provided feedback yet, pause and request input
    if not ctx.resume_inputs:
        summary = (
            f"📚 **StudyBuddy Planner Draft**\n\n"
            f"**Weekly Study Schedule:**\n{node_input.get('scheduler_summary')}\n\n"
            f"**Exam Prep Milestones:**\n{node_input.get('prep_summary')}\n\n"
            f"**Detailed Itinerary:**\n{node_input.get('final_itinerary')}\n\n"
            f"Please review the proposed plan. Do you want to 'approve' it or 'adjust' it? (e.g. Reply 'approve' or describe your adjustments)"
        )
        yield RequestInput(
            interrupt_id="user_feedback",
            message=summary
        )
        return
    
    # If we are resuming, read the user feedback
    feedback = ctx.resume_inputs.get("user_feedback", "").strip()
    logger.info(f"User feedback received: {feedback}")
    
    if "approve" in feedback.lower():
        yield Event(
            route="approve",
            output=node_input,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="✅ Plan approved! Saving schedule to calendar...")]
            )
        )
    else:
        # Route back to orchestrator for adjustment
        yield Event(
            route="adjust",
            output=feedback,
            state={"adjustment_feedback": feedback}
        )

# Node 5: Final Output Node
def final_output_node(ctx: Context, node_input: dict) -> AsyncGenerator[Event, None]:
    """Displays the final status of the study plan process."""
    if node_input.get("status") == "rejected":
        yield Event(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=f"Process terminated: {node_input.get('message')}")]
            )
        )
        yield Event(output=node_input)
        return

    success_message = (
        f"🎉 **Your StudyBuddy Plan is Finalized!**\n\n"
        f"📅 **Approved Schedule Summary:**\n{node_input.get('scheduler_summary')}\n\n"
        f"🏆 **Exam Prep Milestones:**\n{node_input.get('prep_summary')}\n\n"
        f"💪 **Detailed Itinerary:**\n{node_input.get('final_itinerary')}\n\n"
        f"Good luck with your study sessions!"
    )
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=success_message)]
        )
    )
    yield Event(output=node_input)

# Create Workflow graph
root_agent = Workflow(
    name="studybuddy_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {'safe': orchestrator_agent, 'security_event': security_event_node}),
        (orchestrator_agent, hitl_review_node),
        (hitl_review_node, {'adjust': orchestrator_agent, 'approve': final_output_node}),
        (security_event_node, final_output_node),
    ],
    rerun_on_resume=True
)

app = App(
    root_agent=root_agent,
    name="app",
)
