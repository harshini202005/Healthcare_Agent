"""
All available tools defined in Mistral function-calling schema format.
The agent uses this registry to decide which tool to invoke.
"""

ALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the medical knowledge base for health information, clinic policies, "
                "specialty guides, and FAQs. Use this FIRST when answering any health question "
                "or when a patient describes symptoms to find the right specialist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'chest pain specialist', 'blood pressure management')",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_doctors",
            "description": "Get the list of available doctors, optionally filtered by medical specialty.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {
                        "type": "string",
                        "description": "Medical specialty to filter by (e.g., 'cardiology', 'dermatology', 'general practice'). Omit to get all doctors.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Get available appointment time slots for a specialty on a specific date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {
                        "type": "string",
                        "description": "Medical specialty (e.g., 'cardiology')",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                    "doctor_id": {
                        "type": "string",
                        "description": "Specific doctor ID to check (optional)",
                    },
                },
                "required": ["specialty", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_doctor_schedule",
            "description": "Get the weekly working schedule for a specific doctor by their ID or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {
                        "type": "string",
                        "description": "Doctor ID (e.g., 'doc_001') or name (e.g., 'Priya Patel')",
                    }
                },
                "required": ["doctor_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a medical appointment for a patient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Patient ID"},
                    "date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)"},
                    "time": {
                        "type": "string",
                        "description": "Appointment time in 15-min intervals (HH:MM, e.g., '09:00', '14:30')",
                    },
                    "specialty": {"type": "string", "description": "Medical specialty"},
                    "reason": {"type": "string", "description": "Reason for visit"},
                    "doctor_id": {
                        "type": "string",
                        "description": "Preferred doctor ID (optional)",
                    },
                },
                "required": ["user_id", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_appointment",
            "description": "Retrieve appointment details using a confirmation number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation_number": {
                        "type": "string",
                        "description": "Appointment confirmation number (e.g., 'APT-12345')",
                    }
                },
                "required": ["confirmation_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment using its confirmation number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation_number": {
                        "type": "string",
                        "description": "Confirmation number of the appointment to cancel",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for cancellation (optional)",
                    },
                },
                "required": ["confirmation_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_diet",
            "description": "Generate a personalized AI-powered diet plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preferences": {
                        "type": "string",
                        "description": "Dietary preference (e.g., 'vegetarian', 'keto', 'diabetic-friendly')",
                    },
                    "calories": {
                        "type": "integer",
                        "description": "Target daily calorie intake (optional)",
                    },
                    "allergies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of food allergies or restrictions",
                    },
                },
                "required": ["preferences"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "general_query",
            "description": "Answer general health and wellness questions. Use search_knowledge_base first to get relevant context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Health question to answer"},
                    "context": {
                        "type": "string",
                        "description": "Additional context from knowledge base search (optional)",
                    },
                },
                "required": ["question"],
            },
        },
    },
]
