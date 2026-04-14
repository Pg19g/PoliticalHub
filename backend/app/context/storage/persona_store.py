"""Store and retrieve political personas from Neo4j."""

import json
import logging
from typing import Dict, Any, Optional, List

from ...storage import Neo4jStorage

logger = logging.getLogger('miroshark.context.persona_store')


class PersonaStore:
    """Stores rich political personas as JSON properties on Neo4j nodes."""

    def __init__(self, storage: Neo4jStorage):
        self.storage = storage

    def save_politician_persona(self, persona: Dict[str, Any]):
        """Save persona to Politician node (merge by name)."""
        name = persona.get("name", "")
        if not name:
            return

        cypher = """
        MERGE (p:Politician {name: $name})
        SET p.persona = $persona_json,
            p.communication_style = $style,
            p.aggression_level = $aggression,
            p.persona_updated_at = datetime()
        """
        persona_json = json.dumps(persona, ensure_ascii=False)
        style = persona.get("communication_profile", {}).get("style", "")
        aggression = persona.get("communication_profile", {}).get("aggression_level", 5)

        with self.storage._driver.session() as session:
            session.run(cypher, name=name, persona_json=persona_json,
                       style=style, aggression=aggression)
        logger.info(f"Saved persona for politician: {name}")

    def save_party_persona(self, persona: Dict[str, Any]):
        """Save persona to Party node."""
        party = persona.get("party", "")
        if not party:
            return

        # Extract short party name for matching
        short_name = party.split("(")[0].strip() if "(" in party else party

        cypher = """
        MERGE (p:Party {name: $name})
        SET p.persona = $persona_json,
            p.ideology = $ideology,
            p.persona_updated_at = datetime()
        """
        persona_json = json.dumps(persona, ensure_ascii=False)
        ideology = persona.get("ideology", "")

        with self.storage._driver.session() as session:
            session.run(cypher, name=short_name, persona_json=persona_json,
                       ideology=ideology)
        logger.info(f"Saved persona for party: {short_name}")

    def get_politician_persona(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve persona for a politician by name."""
        cypher = """
        MATCH (p:Politician)
        WHERE toLower(p.name) CONTAINS toLower($name) AND p.persona IS NOT NULL
        RETURN p.persona AS persona
        LIMIT 1
        """
        with self.storage._driver.session() as session:
            result = session.run(cypher, name=name)
            record = result.single()
            if record and record["persona"]:
                return json.loads(record["persona"])
        return None

    def get_party_persona(self, party: str) -> Optional[Dict[str, Any]]:
        """Retrieve persona for a party by name."""
        cypher = """
        MATCH (p:Party)
        WHERE toLower(p.name) CONTAINS toLower($party) AND p.persona IS NOT NULL
        RETURN p.persona AS persona
        LIMIT 1
        """
        with self.storage._driver.session() as session:
            result = session.run(cypher, party=party)
            record = result.single()
            if record and record["persona"]:
                return json.loads(record["persona"])
        return None

    def get_persona_for_agent(self, entity_name: str, entity_party: str = "") -> Optional[str]:
        """Get best matching persona text for agent enrichment.
        Tries politician first, falls back to party persona."""

        # Try individual politician persona
        persona = self.get_politician_persona(entity_name)
        if persona:
            return self._format_persona_text(persona, tier="politician")

        # Fall back to party persona
        if entity_party:
            persona = self.get_party_persona(entity_party)
            if persona:
                return self._format_persona_text(persona, tier="party")

        return None

    def _format_persona_text(self, persona: Dict[str, Any], tier: str) -> str:
        """Format persona dict into context text for agent injection."""
        parts = []

        comm = persona.get("communication_profile", {})
        if comm:
            parts.append(f"Styl komunikacji: {comm.get('style', '?')} "
                        f"(agresja: {comm.get('aggression_level', '?')}/10, "
                        f"emocjonalność: {comm.get('emotional_appeal', '?')}/10)")

        phrases = persona.get("signature_phrases", [])
        if phrases:
            parts.append("Typowe frazy: " + ", ".join(f'"{p}"' for p in phrases[:3]))

        examples = persona.get("example_statements", [])
        if examples:
            ex_lines = []
            for ex in examples[:3]:
                ex_lines.append(f'- [{ex.get("tone","")}] "{ex.get("quote","")}" (kontekst: {ex.get("context","")})')
            parts.append("Przykładowe wypowiedzi:\n" + "\n".join(ex_lines))

        tactics = persona.get("debate_tactics", [])
        if tactics:
            parts.append("Taktyki debaty: " + "; ".join(tactics[:3]))

        crisis = persona.get("crisis_playbook", {})
        if crisis:
            parts.append(f"Reakcja na kryzys: {crisis.get('default_reaction', '?')}")

        voter = persona.get("voter_appeal", persona.get("voter_base", {}))
        if voter:
            parts.append(f"Elektorat: {voter.get('demographics', '?')}")

        prefix = "PROFIL POLITYKA" if tier == "politician" else "PROFIL PARTII"
        name = persona.get("name", persona.get("party", "?"))
        return f"### {prefix}: {name}\n" + "\n".join(parts)

    def get_fresh_persona_names(self, ttl_days: int = 14) -> set:
        """Return set of names that have personas newer than ttl_days."""
        cypher = """
        MATCH (p)
        WHERE (p:Politician OR p:Party)
          AND p.persona IS NOT NULL
          AND p.persona_updated_at IS NOT NULL
          AND p.persona_updated_at > datetime() - duration({days: $ttl_days})
        RETURN p.name AS name
        """
        names = set()
        with self.storage._driver.session() as session:
            result = session.run(cypher, ttl_days=ttl_days)
            for r in result:
                names.add(r["name"])
        return names

    def stats(self) -> Dict[str, int]:
        """Count politicians and parties with personas."""
        result = {"politicians_with_persona": 0, "parties_with_persona": 0}
        with self.storage._driver.session() as session:
            r = session.run("MATCH (p:Politician) WHERE p.persona IS NOT NULL RETURN count(p) AS cnt")
            result["politicians_with_persona"] = r.single()["cnt"]
            r = session.run("MATCH (p:Party) WHERE p.persona IS NOT NULL RETURN count(p) AS cnt")
            result["parties_with_persona"] = r.single()["cnt"]
        return result
