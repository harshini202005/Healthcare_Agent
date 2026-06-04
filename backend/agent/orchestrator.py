"""
Agentic orchestrator: uses Mistral function calling to route, reason, and respond.
Streams Server-Sent Events (SSE) back to the frontend.
"""

import json
import os
import logging
from datetime import datetime
from typing import AsyncGenerator

from backend.agent import session as session_store
from backend.agent.tools_registry import ALL_TOOLS
from backend.mcp import call_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an intelligent Healthcare Assistant for a medical clinic. Today's date is {today}.

Your capabilities:
- Help patients find the right doctor based on their symptoms or specialty needs
- Check appointment availability and book/cancel appointments
- Answer health and wellness questions using the knowledge base
- Generate personalized diet plans
- Look up doctor schedules

Behavior rules:
1. For ANY health question or symptom description → ALWAYS call search_knowledge_base first to ground your answer in verified medical content.
2. For symptom-to-specialist queries → search knowledge base, then call get_doctors with the appropriate specialty.
3. For multi-step tasks (e.g., "find a cardiologist and book for tomorrow") → chain tools automatically without asking the user for intermediate steps you can infer.
4. Be empathetic, clear, and concise. Avoid overly long responses.
5. Always add a disclaimer when giving medical advice: remind the user to consult a healthcare professional.
6. If a patient asks something outside healthcare → politely decline and redirect to health topics.
7. For emergencies (chest pain, stroke signs, severe bleeding) → immediately direct them to call emergency services.

Format your final responses using simple markdown (bold **text**, bullet lists, line breaks). Do not use HTML.
"""

TOOL_LABELS = {
    "search_knowledge_base": "Searching medical knowledge base",
    "get_doctors": "Looking up available doctors",
    "get_available_slots": "Checking appointment availability",
    "get_doctor_schedule": "Fetching doctor schedule",
    "book_appointment": "Booking appointment",
    "get_appointment": "Retrieving appointment details",
    "cancel_appointment": "Cancelling appointment",
    "generate_diet": "Generating personalized diet plan",
    "general_query": "Answering health question",
}


def _sse(event_data: dict) -> str:
    return f"data: {json.dumps(event_data)}\n\n"


def _sanitize_history(history: list) -> list:
    """
    Walk the history and remove any assistant+tool_calls block where the number of
    following tool-response messages doesn't exactly match the number of tool calls.
    Mistral rejects requests where these counts differ (error 3230).
    """
    sanitized = []
    i = 0
    while i < len(history):
        msg = history[i]
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            expected_ids = {tc["id"] for tc in msg["tool_calls"]}
            # Collect all consecutive tool responses that follow
            j = i + 1
            tool_responses = []
            while j < len(history) and history[j]["role"] == "tool":
                tool_responses.append(history[j])
                j += 1
            response_ids = {r.get("tool_call_id") for r in tool_responses}
            if expected_ids == response_ids:
                sanitized.append(msg)
                sanitized.extend(tool_responses)
            else:
                logger.warning(
                    f"Dropping incomplete tool-call block: expected={expected_ids} got={response_ids}"
                )
            i = j
        elif msg["role"] == "tool":
            # Orphaned tool response with no preceding assistant+tool_calls — drop it
            logger.warning(f"Dropping orphaned tool message: {msg.get('name')}")
            i += 1
        else:
            sanitized.append(msg)
            i += 1
    return sanitized


async def run(session_id: str, user_message: str) -> AsyncGenerator[str, None]:
    """
    Main agent loop. Yields SSE strings:
      {"type": "tool_use", "tool": "...", "label": "..."}
      {"type": "final", "content": "..."}
      {"type": "error", "message": "..."}
    """
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key or api_key == "your-mistral-api-key-here":
        yield _sse({"type": "error", "message": "Mistral API key not configured."})
        return

    from mistralai import Mistral
    client = Mistral(api_key=api_key)

    history = _sanitize_history(session_store.get_history(session_id))
    history.append({"role": "user", "content": user_message})

    system_msg = {"role": "system", "content": SYSTEM_PROMPT.format(today=datetime.now().strftime("%Y-%m-%d"))}

    max_iterations = 6

    try:
        for _ in range(max_iterations):
            response = client.chat.complete(
                model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
                messages=[system_msg] + history,
                tools=ALL_TOOLS,
                tool_choice="auto",
            )

            choice = response.choices[0]
            message = choice.message
            finish_reason = choice.finish_reason

            if finish_reason == "tool_calls" and message.tool_calls:
                # Add assistant message with tool calls to history
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
                history.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": tool_call_dicts,
                    }
                )

                # Execute each tool call
                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    label = TOOL_LABELS.get(tool_name, f"Using {tool_name}")
                    yield _sse({"type": "tool_use", "tool": tool_name, "label": label})

                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        args = {}

                    result = call_tool(tool_name, args)

                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "content": json.dumps(result),
                        }
                    )

            else:
                # Final text response
                final_content = message.content or "I'm sorry, I couldn't generate a response."
                history.append({"role": "assistant", "content": final_content})
                session_store.save_history(session_id, history)
                yield _sse({"type": "final", "content": final_content})
                return

        # Max iterations hit — save only the clean portion (no dangling tool calls)
        session_store.save_history(session_id, _sanitize_history(history))
        yield _sse({"type": "final", "content": "I've completed my research. How else can I help you?"})

    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        # Save cleaned history so the next turn starts from a consistent state
        session_store.save_history(session_id, _sanitize_history(history))
        yield _sse({"type": "error", "message": f"Something went wrong: {str(e)}"})
