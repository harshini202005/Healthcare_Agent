
import os
from mistralai import Mistral

def generate(preferences, calories=None, allergies=None):
    """
    Generate a personalized diet plan based on preferences.
    
    Args:
        preferences: Dietary preference (vegetarian, vegan, keto, etc.)
        calories: Target daily calorie intake (optional)
        allergies: List of food allergies or restrictions (optional)
    """
    print(f"\n🔧 TOOL CALLED: generate_diet")
    print(f"   Preferences: {preferences}")
    print(f"   Calories: {calories or 'Not specified'}")
    print(f"   Allergies: {allergies or 'None'}")
    
    if allergies is None:
        allergies = []
    
    api_key = os.getenv("MISTRAL_API_KEY")
    
    if not api_key or api_key == "your-mistral-api-key-here":
        print(f"   ⚠️ Mistral API key not configured, using template response")
        diet_plan = {
            "error": False,
            "message": "🥗 Here's your personalized diet plan",
            "preference": preferences,
            "daily_calories": calories or 2000,
            "allergies": allergies or ["None"],
            "meals": {
                "Breakfast": f"Healthy {preferences} breakfast - oatmeal with berries (400 cal)",
                "Morning Snack": "Greek yogurt with honey (150 cal)",
                "Lunch": f"Nutritious {preferences} lunch - quinoa bowl with vegetables (500 cal)",
                "Afternoon Snack": "Fresh fruits and nuts (200 cal)",
                "Dinner": f"Balanced {preferences} dinner with protein and veggies (600 cal)",
                "Evening": "Herbal tea (0 cal)"
            },
            "tips": [
                "💧 Stay hydrated - drink 8-10 glasses of water daily",
                "🥗 Include variety of colorful vegetables",
                "🍽️ Practice portion control",
                "🧘 Eat mindfully and avoid distractions",
                "🏃 Combine with 30 minutes of daily exercise"
            ],
            "note": "⚠️ Configure Mistral API key in .env for AI-powered recommendations"
        }
        return diet_plan
    
    try:
        client = Mistral(api_key=api_key)

        allergy_str = ', '.join(allergies) if allergies else 'None'
        calorie_target = calories or 2000

        prompt = f"""Create a one-day diet plan with these exact constraints:
- Dietary style: {preferences}
- Total daily calories: {calorie_target} kcal (±50 kcal tolerance)
- ALLERGIES/RESTRICTIONS — MUST AVOID: {allergy_str}

CRITICAL: If allergies are listed, every single meal and ingredient MUST be free of those allergens. Check each item carefully.

Respond in this exact format — no deviations:

## Breakfast (~XX kcal)
[Meal name]: [ingredients]

## Morning Snack (~XX kcal)
[Meal name]: [ingredients]

## Lunch (~XX kcal)
[Meal name]: [ingredients]

## Afternoon Snack (~XX kcal)
[Meal name]: [ingredients]

## Dinner (~XX kcal)
[Meal name]: [ingredients]

## Daily Total: ~XX kcal

## Nutrition Tips
- [Tip 1]
- [Tip 2]
- [Tip 3]

⚠️ This plan is for informational purposes. Consult a registered dietitian for personalized medical nutrition therapy."""

        response = client.chat.complete(
            model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a registered dietitian. You ONLY output diet plans in the exact format requested. "
                        "You never fabricate calorie counts — use standard nutritional reference values. "
                        f"CRITICAL: The user has these allergies/restrictions: {allergy_str}. "
                        "Before finalizing each meal, verify it contains NONE of these allergens."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=900
        )
        
        diet_content = response.choices[0].message.content
        print(f"   ✅ Result: AI diet plan generated with Mistral")
        
        return {
            "error": False,
            "message": "🥗 Your AI-Powered Personalized Diet Plan (Mistral AI)",
            "plan": diet_content,
            "preference": preferences,
            "daily_calories": calories or 2000,
            "allergies": allergies or ["None"]
        }
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return {
            "error": True,
            "message": f"Failed to generate diet plan: {str(e)}",
            "fallback": "Please check your Mistral API key configuration in .env file"
        }
