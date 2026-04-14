"""Generate rich political personas using Gemini with Search Grounding."""

import json
import logging
import time
from typing import List, Dict, Any, Optional

import requests

from ...config import Config

logger = logging.getLogger('miroshark.context.persona')

GEMINI_API = 'https://generativelanguage.googleapis.com/v1beta'

# Top 30 Polish politicians to generate individual personas for
TOP_POLITICIANS = [
    "Donald Tusk", "Jarosław Kaczyński", "Andrzej Duda", "Szymon Hołownia",
    "Rafał Trzaskowski", "Mateusz Morawiecki", "Włodzimierz Czarzasty",
    "Krzysztof Bosak", "Sławomir Mentzen", "Władysław Kosiniak-Kamysz",
    "Marcin Kierwiński", "Mariusz Błaszczak", "Zbigniew Ziobro",
    "Robert Biedroń", "Adrian Zandberg", "Radosław Sikorski",
    "Patryk Jaki", "Przemysław Czarnek", "Izabela Leszczyna",
    "Grzegorz Braun", "Borys Budka", "Barbara Nowacka",
    "Magdalena Biejat", "Andrzej Domański", "Jacek Sasin",
    "Ryszard Terlecki", "Sebastian Kaleta", "Dariusz Matecki",
    "Janusz Korwin-Mikke", "Paulina Hennig-Kloska"
]

# Party profiles for generic tier-2 personas
PARTIES = [
    "Prawo i Sprawiedliwość (PiS)",
    "Koalicja Obywatelska (KO/Platforma Obywatelska)",
    "Lewica (Nowa Lewica, Razem)",
    "Polska 2050 / Trzecia Droga",
    "Polskie Stronnictwo Ludowe (PSL)",
    "Konfederacja",
]

POLITICIAN_PROMPT = """Jesteś ekspertem od polskiej polityki. Wygeneruj szczegółowy profil komunikacyjny polityka na podstawie jego publicznych wypowiedzi, wywiadów, wystąpień w Sejmie i aktywności w mediach.

POLITYK: {name}

Odpowiedz WYŁĄCZNIE w formacie JSON (bez markdown, bez komentarzy):
{{
  "name": "{name}",
  "communication_profile": {{
    "style": "opis stylu komunikacji w 2-3 słowach",
    "aggression_level": <1-10>,
    "formality": <1-10>,
    "irony_usage": <1-10>,
    "data_driven": <1-10>,
    "emotional_appeal": <1-10>
  }},
  "signature_phrases": ["fraza 1", "fraza 2", "fraza 3"],
  "example_statements": [
    {{"context": "kontekst wypowiedzi", "quote": "prawdziwy lub typowy cytat", "tone": "ton"}},
    {{"context": "kontekst", "quote": "cytat", "tone": "ton"}},
    {{"context": "kontekst", "quote": "cytat", "tone": "ton"}}
  ],
  "key_topics": ["temat1", "temat2", "temat3", "temat4", "temat5"],
  "avoided_topics": ["temat1", "temat2"],
  "debate_tactics": ["taktyka 1", "taktyka 2", "taktyka 3"],
  "relationships": {{
    "allies": ["imię1", "imię2"],
    "rivals": ["imię1", "imię2"],
    "style_toward_rivals": "opis"
  }},
  "crisis_playbook": {{
    "default_reaction": "opis",
    "media_strategy": "opis",
    "example": "konkretny przykład reakcji na kryzys"
  }},
  "voter_appeal": {{
    "demographics": "opis grupy docelowej",
    "emotional_triggers": ["trigger1", "trigger2"],
    "what_mobilizes": "opis"
  }},
  "social_media": {{
    "platforms": ["platforma1"],
    "posting_style": "opis",
    "engagement_pattern": "opis"
  }}
}}"""

PARTY_PROMPT = """Jesteś ekspertem od polskiej polityki. Wygeneruj profil komunikacyjny PARTII — jak typowy poseł tej partii się komunikuje, jakie ma poglądy, jak reaguje na kryzysy.

PARTIA: {party}

Odpowiedz WYŁĄCZNIE w formacie JSON (bez markdown, bez komentarzy):
{{
  "party": "{party}",
  "ideology": "opis ideologii w 2-3 zdaniach",
  "communication_profile": {{
    "style": "typowy styl komunikacji posła tej partii",
    "aggression_level": <1-10>,
    "formality": <1-10>,
    "emotional_appeal": <1-10>
  }},
  "key_topics": ["temat1", "temat2", "temat3", "temat4", "temat5"],
  "signature_phrases": ["fraza 1", "fraza 2", "fraza 3"],
  "example_statements": [
    {{"context": "kontekst", "quote": "typowa wypowiedź posła tej partii", "tone": "ton"}},
    {{"context": "kontekst", "quote": "wypowiedź", "tone": "ton"}}
  ],
  "debate_tactics": ["taktyka 1", "taktyka 2"],
  "voter_base": {{
    "demographics": "opis elektoratu",
    "emotional_triggers": ["trigger1", "trigger2"],
    "what_mobilizes": "opis"
  }},
  "typical_mp_profile": {{
    "age_range": "zakres wiekowy",
    "background": "typowe wykształcenie/kariera",
    "social_media_behavior": "opis"
  }}
}}"""


class PersonaGenerator:
    """Generates rich political personas using Gemini with Search Grounding."""

    def __init__(self):
        self.api_key = Config.EMBEDDING_API_KEY  # Gemini key
        if not self.api_key:
            raise ValueError("EMBEDDING_API_KEY (Gemini) required for persona generation")

    def _call_gemini_grounded(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call Gemini with Search Grounding, return parsed JSON."""
        url = f"{GEMINI_API}/models/gemini-2.5-flash:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
            }
        }

        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            # Extract text from response
            text = ""
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        text += part["text"]

            if not text:
                return None

            # Clean markdown JSON fences if present
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            return json.loads(text)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
            logger.debug(f"Raw text: {text[:500]}")
            return None
        except Exception as e:
            logger.error(f"Gemini grounded search failed: {e}")
            return None

    def generate_politician_persona(self, name: str) -> Optional[Dict[str, Any]]:
        """Generate a rich persona for a single politician."""
        prompt = POLITICIAN_PROMPT.format(name=name)
        result = self._call_gemini_grounded(prompt)
        if result:
            logger.info(f"Generated persona for {name}")
        else:
            logger.warning(f"Failed to generate persona for {name}")
        return result

    def generate_party_persona(self, party: str) -> Optional[Dict[str, Any]]:
        """Generate a generic party persona."""
        prompt = PARTY_PROMPT.format(party=party)
        result = self._call_gemini_grounded(prompt)
        if result:
            logger.info(f"Generated party persona for {party}")
        else:
            logger.warning(f"Failed to generate party persona for {party}")
        return result

    def generate_all(self, delay: float = 2.0) -> Dict[str, Any]:
        """Generate all personas (top politicians + parties)."""
        results = {"politicians": [], "parties": [], "errors": []}

        # Tier 1: Individual politicians
        for i, name in enumerate(TOP_POLITICIANS):
            persona = self.generate_politician_persona(name)
            if persona:
                results["politicians"].append(persona)
            else:
                results["errors"].append(f"politician:{name}")

            if i < len(TOP_POLITICIANS) - 1:
                time.sleep(delay)

            if (i + 1) % 10 == 0:
                logger.info(f"Persona progress: {i + 1}/{len(TOP_POLITICIANS)} politicians")

        # Tier 2: Party personas
        for party in PARTIES:
            persona = self.generate_party_persona(party)
            if persona:
                results["parties"].append(persona)
            else:
                results["errors"].append(f"party:{party}")
            time.sleep(delay)

        logger.info(f"Persona generation complete: {len(results['politicians'])} politicians, "
                    f"{len(results['parties'])} parties, {len(results['errors'])} errors")
        return results
