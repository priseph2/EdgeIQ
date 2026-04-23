"""
Claude API integration for on-demand match analysis.
Uses prompt caching on the system prompt to reduce token costs.
Returns structured JSON: key_factors, confidence_narrative, risk, suggested_stake_pct.
"""

import json
import logging
from typing import Optional
import anthropic
from config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[anthropic.Anthropic] = None

SYSTEM_PROMPT = """You are EdgeIQ's expert sports betting analyst. You have deep knowledge of:
- NBA basketball: team dynamics, rest schedules, coaching adjustments, home-court effects
- European club football (Premier League, La Liga, Bundesliga, Serie A, Ligue 1): form, xG, injuries, European fatigue, manager tactics
- Betting markets: line movement, closing line value, bookmaker pricing, value identification

Your role is to provide concise, high-signal analysis that complements a statistical ML model.
Focus on factors the model cannot capture: injuries to key players, motivational context, tactical mismatches, recent news.

Always respond with valid JSON only. No markdown, no preamble."""

ANALYSIS_PROMPT_TEMPLATE = """Analyze this upcoming match for betting purposes.

Match: {home_team} vs {away_team}
Competition: {league} | Sport: {sport}
Kick-off: {start_time}

ML Model Output:
- Home win probability: {home_prob:.1%}
- Draw probability: {draw_prob}
- Away win probability: {away_prob:.1%}
- Model confidence: {confidence}
- Model pick: {pick}

Recent form ({home_team}, last 5): {home_form}
Recent form ({away_team}, last 5): {away_form}

Best available odds:
- Home: {best_home_odds} ({home_implied:.1%} implied)
- Draw: {best_draw_odds}
- Away: {best_away_odds} ({away_implied:.1%} implied)

Recent news / context:
{context}

Respond with this exact JSON structure:
{{
  "key_factors": ["factor 1", "factor 2", "factor 3"],
  "model_alignment": "agrees|disagrees|neutral",
  "model_alignment_reason": "one sentence",
  "confidence_narrative": "2-3 sentences explaining the bet case",
  "main_risk": "one sentence on the biggest risk to this bet",
  "suggested_stake_pct": 1.5,
  "value_assessment": "strong_value|moderate_value|fair|avoid",
  "pick": "home|draw|away|no_bet"
}}"""


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    return _client


def format_form(results: list[str]) -> str:
    """Format last 5 results as e.g. 'W W L D W'"""
    if not results:
        return "N/A"
    return " ".join(r.upper() for r in results[-5:])


async def analyze_match(
    home_team: str,
    away_team: str,
    league: str,
    sport: str,
    start_time: str,
    prediction: dict,
    home_form: list[str],
    away_form: list[str],
    best_home_odds: Optional[float],
    best_draw_odds: Optional[float],
    best_away_odds: Optional[float],
    context: str = "No additional context available.",
) -> dict:
    """
    Call Claude API with prompt caching on system prompt.
    Returns parsed JSON dict.
    """
    draw_prob_str = f"{prediction['draw_prob']:.1%}" if prediction.get("draw_prob") else "N/A (basketball)"
    draw_odds_str = f"{best_draw_odds:.2f}" if best_draw_odds else "N/A"
    home_implied = (1 / best_home_odds) if best_home_odds else 0
    away_implied = (1 / best_away_odds) if best_away_odds else 0

    user_content = ANALYSIS_PROMPT_TEMPLATE.format(
        home_team=home_team,
        away_team=away_team,
        league=league,
        sport=sport,
        start_time=start_time,
        home_prob=prediction["home_prob"],
        draw_prob=draw_prob_str,
        away_prob=prediction["away_prob"],
        confidence=prediction["confidence"],
        pick=prediction["pick"],
        home_form=format_form(home_form),
        away_form=format_form(away_form),
        best_home_odds=f"{best_home_odds:.2f}" if best_home_odds else "N/A",
        best_draw_odds=draw_odds_str,
        best_away_odds=f"{best_away_odds:.2f}" if best_away_odds else "N/A",
        home_implied=home_implied,
        away_implied=away_implied,
        context=context,
    )

    client = get_client()
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip()
        # Strip any accidental markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        logger.info(
            f"Claude analysis: {home_team} vs {away_team} | "
            f"pick={result.get('pick')} | value={result.get('value_assessment')} | "
            f"cache_read={response.usage.cache_read_input_tokens}"
        )
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}")
        return _fallback_analysis(prediction)
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return _fallback_analysis(prediction)


def _fallback_analysis(prediction: dict) -> dict:
    return {
        "key_factors": ["Model-based prediction only", "No contextual analysis available"],
        "model_alignment": "neutral",
        "model_alignment_reason": "AI analysis unavailable, using model output only.",
        "confidence_narrative": f"Model picks {prediction['pick']} with {prediction['confidence']} confidence. Manual review recommended.",
        "main_risk": "AI analysis unavailable.",
        "suggested_stake_pct": 1.0,
        "value_assessment": "fair",
        "pick": prediction["pick"],
    }
