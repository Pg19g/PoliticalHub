"""Neo4j storage for Polish political entities and relationships."""

import logging
from typing import List, Dict, Any, Optional

from ...storage import Neo4jStorage

logger = logging.getLogger('miroshark.context.neo4j_political')


class Neo4jPolitical:
    """CRUD for political entities in the existing Neo4j instance."""

    def __init__(self, storage: Neo4jStorage):
        self.storage = storage
        self._ensure_constraints()

    def _ensure_constraints(self):
        """Create uniqueness constraints for political nodes."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Politician) REQUIRE p.sejm_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Party) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (b:Bill) REQUIRE b.number IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Committee) REQUIRE c.name IS UNIQUE",
        ]
        with self.storage._driver.session() as session:
            for cypher in constraints:
                try:
                    session.run(cypher)
                except Exception as e:
                    logger.warning(f"Constraint creation warning: {e}")
        logger.info("Political graph constraints ensured")

    def upsert_politician(self, data: Dict[str, Any]):
        """Create or update a Politician node."""
        cypher = """
        MERGE (p:Politician {sejm_id: $sejm_id})
        SET p.name = $name,
            p.party = $party,
            p.role = $role,
            p.district = $district,
            p.photo_url = $photo_url,
            p.updated_at = datetime()
        WITH p
        MERGE (party:Party {name: $party})
        MERGE (p)-[:MEMBER_OF]->(party)
        """
        with self.storage._driver.session() as session:
            session.run(cypher, **data)

    def upsert_bill(self, data: Dict[str, Any]):
        """Create or update a Bill node."""
        cypher = """
        MERGE (b:Bill {number: $number})
        SET b.title = $title,
            b.category = $category,
            b.status = $status,
            b.date = $date,
            b.updated_at = datetime()
        """
        with self.storage._driver.session() as session:
            session.run(cypher, **data)

    def record_vote(self, sejm_id: int, bill_number: str, vote: str):
        """Record a politician's vote on a bill."""
        cypher = """
        MATCH (p:Politician {sejm_id: $sejm_id})
        MATCH (b:Bill {number: $bill_number})
        MERGE (p)-[v:VOTED]->(b)
        SET v.vote = $vote, v.recorded_at = datetime()
        """
        with self.storage._driver.session() as session:
            session.run(cypher, sejm_id=sejm_id, bill_number=bill_number, vote=vote)

    def upsert_committee(self, name: str, committee_type: str):
        """Create or update a Committee node."""
        cypher = """
        MERGE (c:Committee {name: $name})
        SET c.type = $type, c.updated_at = datetime()
        """
        with self.storage._driver.session() as session:
            session.run(cypher, name=name, type=committee_type)

    def set_committee_membership(self, sejm_id: int, committee_name: str):
        """Link a politician to a committee."""
        cypher = """
        MATCH (p:Politician {sejm_id: $sejm_id})
        MATCH (c:Committee {name: $committee_name})
        MERGE (p)-[:SITS_ON]->(c)
        """
        with self.storage._driver.session() as session:
            session.run(cypher, sejm_id=sejm_id, committee_name=committee_name)

    def update_polls(self, polls: Dict[str, float]):
        """Update party poll percentages. Input: {"PiS": 32.1, "KO": 30.5, ...}"""
        cypher = """
        MERGE (p:Party {name: $name})
        SET p.polls_pct = $pct, p.polls_updated_at = datetime()
        """
        with self.storage._driver.session() as session:
            for party_name, pct in polls.items():
                session.run(cypher, name=party_name, pct=pct)
        logger.info(f"Updated polls for {len(polls)} parties")

    def get_party_stances(self, topic: str) -> List[Dict[str, Any]]:
        """Get party voting patterns on bills matching a topic keyword."""
        cypher = """
        MATCH (p:Politician)-[v:VOTED]->(b:Bill)
        WHERE b.title CONTAINS $topic OR b.category CONTAINS $topic
        MATCH (p)-[:MEMBER_OF]->(party:Party)
        WITH party.name AS party_name,
             v.vote AS vote,
             count(*) AS cnt
        RETURN party_name, vote, cnt
        ORDER BY party_name, cnt DESC
        """
        with self.storage._driver.session() as session:
            result = session.run(cypher, topic=topic)
            return [dict(r) for r in result]

    def get_polls(self) -> Dict[str, float]:
        """Get latest poll percentages for all parties."""
        cypher = """
        MATCH (p:Party)
        WHERE p.polls_pct IS NOT NULL
        RETURN p.name AS name, p.polls_pct AS pct
        ORDER BY p.polls_pct DESC
        """
        with self.storage._driver.session() as session:
            result = session.run(cypher)
            return {r['name']: r['pct'] for r in result}

    def get_politician_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find politician by name (case-insensitive partial match)."""
        cypher = """
        MATCH (p:Politician)
        WHERE toLower(p.name) CONTAINS toLower($name)
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(party:Party)
        RETURN p.name AS name, p.sejm_id AS sejm_id, p.role AS role,
               party.name AS party, party.polls_pct AS party_polls
        LIMIT 5
        """
        with self.storage._driver.session() as session:
            result = session.run(cypher, name=name)
            records = [dict(r) for r in result]
            return records[0] if records else None
