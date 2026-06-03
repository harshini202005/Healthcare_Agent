import os
import logging
from mistralai import Mistral

logger = logging.getLogger(__name__)

_HEALTH_KEYWORDS = [
    "symptom", "disease", "condition", "diagnosis", "illness", "disorder",
    "infection", "fever", "cough", "headache", "pain", "ache", "nausea", "vomit",
    "diabetes", "blood pressure", "hypertension", "asthma", "arthritis", "cancer",
    "allergy", "allergic", "rash", "inflammation", "fracture", "injury", "wound",
    "treatment", "medicine", "medication", "prescription", "therapy", "cure",
    "surgery", "vaccine", "vaccination", "dose", "dosage", "side effect",
    "doctor", "physician", "specialist", "hospital", "clinic", "emergency",
    "healthcare", "appointment", "consultation",
    "heart", "lung", "kidney", "liver", "brain", "blood", "bone", "muscle",
    "immune", "nervous system", "digestive", "respiratory", "cardiovascular",
    "nutrition", "nutrient", "vitamin", "mineral", "calorie", "protein",
    "carbohydrate", "cholesterol", "diet plan", "meal plan", "dietary",
    "vegetarian", "vegan", "keto", "gluten", "lactose", "diabetic diet",
    "mental health", "anxiety", "depression", "stress", "insomnia", "sleep disorder",
    "sleep", "counseling", "psychiatrist", "psychologist",
    "fitness", "exercise", "workout", "wellness", "healthy lifestyle",
    "weight loss", "obesity", "bmi", "physical activity",
    "health", "medical", "clinical", "patient", "healthy", "unhealthy",
    "prevent", "prevention", "risk factor", "chronic", "acute",
]


def _is_health_related(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _HEALTH_KEYWORDS)


def answer(question: str, context: str = None) -> dict:
    """Answer general health and wellness questions using Mistral AI."""
    logger.info(f"general_query: {question!r}")

    if not _is_health_related(question):
        return {
            "error": True,
            "message": "I can only answer health-related questions.",
            "suggestion": (
                "Please ask about health topics like:\n"
                "• Medical conditions and symptoms\n"
                "• Treatments and medications\n"
                "• Diet and nutrition\n"
                "• Exercise and fitness\n"
                "• Mental health and wellness"
            ),
        }

    api_key = os.getenv("MISTRAL_API_KEY")

    if not api_key or api_key == "your-mistral-api-key-here":
        logger.warning("Mistral API key not configured — returning generic response")
        return {
            "answer": "I can help with health questions. Could you please be more specific about your health concern?",
            "source": "template",
            "disclaimer": "⚕️ This is general information. Please consult a healthcare professional for medical advice.",
        }

    try:
        client = Mistral(api_key=api_key)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a certified healthcare information assistant.\n"
                    "SCOPE: Only answer questions about medical conditions, symptoms, treatments, medications, "
                    "nutrition, fitness, mental health, or healthcare services.\n"
                    "ACCURACY: Only state well-established medical facts. Never invent drug names, dosages, or diagnoses.\n"
                    "FORMAT: 2-4 sentence answer, then a short bullet list if applicable. "
                    'End with: "⚕️ Consult a healthcare professional before making medical decisions."\n'
                    "HARD RULES: Never diagnose. Never recommend prescription doses. "
                    'If emergency: say "Call emergency services (911) immediately."'
                ),
            },
            {"role": "user", "content": question},
        ]

        if context:
            messages.insert(1, {
                "role": "system",
                "content": f"Patient context (use only for relevance, do not expose): {context}",
            })

        response = client.chat.complete(model="mistral-small-latest", messages=messages)
        logger.info("general_query response generated")
        return {
            "answer": response.choices[0].message.content,
            "source": "mistral_ai",
            "disclaimer": "⚕️ This information is for educational purposes. Consult a healthcare professional for personalised advice.",
        }

    except Exception as e:
        logger.error(f"general_query error: {e}")
        return {
            "error": True,
            "message": f"Unable to process your question: {e}",
            "suggestion": "Please try again or rephrase your health question.",
        }
