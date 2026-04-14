"""Generate rich political personas using Gemini with Search Grounding.

Features:
- Retry with JSON repair on parse failures (3 attempts)
- Parallel generation via ThreadPoolExecutor (5 concurrent)
- TTL-based skip: won't regenerate if persona < 14 days old
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

import requests

from ...config import Config

logger = logging.getLogger('miroshark.context.persona')

GEMINI_API = 'https://generativelanguage.googleapis.com/v1beta'
PERSONA_TTL_DAYS = 14
MAX_RETRIES = 3
MAX_WORKERS = 5

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

JSON_REPAIR_PROMPT = """Poniższy tekst miał być poprawnym JSON-em ale zawiera błędy składniowe.
Napraw go i zwróć WYŁĄCZNIE poprawny JSON (bez markdown, bez komentarzy, bez ```):

{raw_text}"""


def _clean_json_text(text: str) -> str:
    """Strip markdown fences and common LLM artifacts from JSON output."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


class PersonaGenerator:
    """Generates rich political personas using Gemini with Search Grounding."""

    def __init__(self):
        self.api_key = Config.EMBEDDING_API_KEY  # Gemini key
        if not self.api_key:
            raise ValueError("EMBEDDING_API_KEY (Gemini) required for persona generation")

    def _call_gemini_grounded(self, prompt: str) -> Optional[str]:
        """Call Gemini with Search Grounding, return raw text."""
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
            resp = requests.post(url, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()

            text = ""
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        text += part["text"]

            return text if text else None

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return None

    def _call_gemini_repair(self, raw_text: str) -> Optional[str]:
        """Call Gemini WITHOUT grounding to repair broken JSON."""
        url = f"{GEMINI_API}/models/gemini-2.5-flash:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": JSON_REPAIR_PROMPT.format(raw_text=raw_text[:3000])}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 4096,
            }
        }

        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            text = ""
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        text += part["text"]
            return text if text else None
        except Exception as e:
            logger.error(f"Gemini repair call failed: {e}")
            return None

    def _generate_with_retry(self, prompt: str, name: str) -> Optional[Dict[str, Any]]:
        """Generate persona with up to MAX_RETRIES attempts, including JSON repair."""
        raw_text = None

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt == 1:
                # First attempt: normal grounded search
                raw_text = self._call_gemini_grounded(prompt)
            elif attempt == 2 and raw_text:
                # Second attempt: repair the broken JSON
                logger.info(f"Retrying {name} with JSON repair (attempt {attempt})")
                raw_text = self._call_gemini_repair(raw_text)
            else:
                # Third attempt: re-generate with stronger JSON instruction
                logger.info(f"Retrying {name} with fresh generation (attempt {attempt})")
                stronger_prompt = prompt + "\n\nKRYTYCZNE: Odpowiedz TYLKO czystym JSON. Bez markdown. Bez ```json. Bez komentarzy. Zacznij od { i zakończ na }."
                raw_text = self._call_gemini_grounded(stronger_prompt)

            if not raw_text:
                continue

            cleaned = _clean_json_text(raw_text)
            try:
                result = json.loads(cleaned)
                if attempt > 1:
                    logger.info(f"Persona for {name} succeeded on attempt {attempt}")
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed for {name} (attempt {attempt}): {e}")
                # Keep raw_text for repair attempt
                continue

        logger.error(f"All {MAX_RETRIES} attempts failed for {name}")
        return None

    def generate_politician_persona(self, name: str) -> Optional[Dict[str, Any]]:
        """Generate a rich persona for a single politician."""
        prompt = POLITICIAN_PROMPT.format(name=name)
        result = self._generate_with_retry(prompt, name)
        if result:
            logger.info(f"Generated persona for {name}")
        else:
            logger.warning(f"Failed to generate persona for {name} after {MAX_RETRIES} retries")
        return result

    def generate_party_persona(self, party: str) -> Optional[Dict[str, Any]]:
        """Generate a generic party persona."""
        prompt = PARTY_PROMPT.format(party=party)
        result = self._generate_with_retry(prompt, party)
        if result:
            logger.info(f"Generated party persona for {party}")
        else:
            logger.warning(f"Failed to generate party persona for {party} after {MAX_RETRIES} retries")
        return result

    def generate_all(self, existing_names: set = None) -> Dict[str, Any]:
        """Generate all personas in parallel, skipping existing fresh ones.

        Args:
            existing_names: Set of names that already have fresh personas (skip these)
        """
        existing_names = existing_names or set()
        results = {"politicians": [], "parties": [], "errors": [], "skipped": []}

        # Filter out politicians with fresh personas
        politicians_to_generate = []
        for name in TOP_POLITICIANS:
            if name in existing_names:
                results["skipped"].append(name)
                logger.info(f"Skipping {name} — persona still fresh")
            else:
                politicians_to_generate.append(name)

        parties_to_generate = []
        for party in PARTIES:
            short = party.split("(")[0].strip() if "(" in party else party
            if short in existing_names:
                results["skipped"].append(party)
                logger.info(f"Skipping {party} — persona still fresh")
            else:
                parties_to_generate.append(party)

        logger.info(f"Generating {len(politicians_to_generate)} politician + "
                    f"{len(parties_to_generate)} party personas "
                    f"({len(results['skipped'])} skipped as fresh)")

        # Parallel politician generation
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self.generate_politician_persona, name): name
                for name in politicians_to_generate
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    persona = future.result()
                    if persona:
                        results["politicians"].append(persona)
                    else:
                        results["errors"].append(f"politician:{name}")
                except Exception as e:
                    logger.error(f"Exception generating persona for {name}: {e}")
                    results["errors"].append(f"politician:{name}")

        # Parallel party generation
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self.generate_party_persona, party): party
                for party in parties_to_generate
            }
            for future in as_completed(futures):
                party = futures[future]
                try:
                    persona = future.result()
                    if persona:
                        results["parties"].append(persona)
                    else:
                        results["errors"].append(f"party:{party}")
                except Exception as e:
                    logger.error(f"Exception generating party persona for {party}: {e}")
                    results["errors"].append(f"party:{party}")

        logger.info(f"Persona generation complete: {len(results['politicians'])} politicians, "
                    f"{len(results['parties'])} parties, {len(results['errors'])} errors, "
                    f"{len(results['skipped'])} skipped")
        return results
