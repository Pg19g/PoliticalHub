"""
Parse simulation_requirement to extract voter groups and create synthetic entities.

Solves the core problem: MiroShark generates agents from NER entities (institutions
like CBOS, ZUS become "agents"), but political simulations need voter groups
defined in the simulation_requirement.

This module:
1. Parses requirement text for group definitions (e.g., "30% wyborcy PiS")
2. Creates synthetic EntityNode objects for each group
3. Filters out non-actor entities from NER (institutions, concepts, funds)
4. Merges NER persons/parties + synthetic voter groups
"""

import re
import uuid
from typing import List, Optional
from dataclasses import field

from .entity_reader import EntityNode, FilteredEntities
from ..utils.logger import get_logger

logger = get_logger('miroshark.requirement_parser')

# Entity types that should NOT become agents (they're context, not actors)
NON_ACTOR_TYPES = {
    'organization', 'institution', 'fund', 'agency',
    'newspublisher', 'researchinstitute', 'governmentagency',
}

# Entity names that should never be agents
NON_ACTOR_NAMES = {
    'cbos', 'zus', 'nfz', 'gus', 'nbp', 'kas', 'knf', 'krs',
    'fundusz kościelny', 'fundusz koscielny',
    'episkopat', 'senat', 'sejm', 'trybunał',
}

# Patterns to detect group definitions in simulation_requirement
# Matches: "30% wyborcy PiS (opis)", "wyborcy KO (25%, opis)", etc.
GROUP_PATTERN = re.compile(
    r'(\d{1,3})%\s*[-–—]?\s*([^,(]+?)(?:\s*\(([^)]*)\))?(?:,|$)',
    re.IGNORECASE
)

# Alternative pattern: "wyborcy PiS (30%, opis)"
GROUP_PATTERN_ALT = re.compile(
    r'([^,(]+?)\s*\((\d{1,3})%[^)]*\)',
    re.IGNORECASE
)


def parse_groups_from_requirement(requirement: str) -> List[dict]:
    """Extract voter group definitions from simulation requirement text.

    Returns list of dicts: [{"name": "wyborcy PiS", "percentage": 30, "description": "..."}]
    """
    groups = []
    seen_names = set()

    # Try primary pattern: "30% wyborcy PiS (opis)"
    for match in GROUP_PATTERN.finditer(requirement):
        pct = int(match.group(1))
        name = match.group(2).strip().rstrip('-–— ')
        desc = match.group(3) or ''

        if name.lower() not in seen_names and pct > 0:
            groups.append({
                'name': name,
                'percentage': pct,
                'description': f"{name} ({desc})" if desc else name,
            })
            seen_names.add(name.lower())

    # Try alternative pattern if primary found nothing
    if not groups:
        for match in GROUP_PATTERN_ALT.finditer(requirement):
            name = match.group(1).strip()
            pct = int(match.group(2))

            if name.lower() not in seen_names and pct > 0:
                groups.append({
                    'name': name,
                    'percentage': pct,
                    'description': name,
                })
                seen_names.add(name.lower())

    if groups:
        logger.info(f"Parsed {len(groups)} voter groups from requirement: "
                    f"{', '.join(g['name'] for g in groups)}")

    return groups


def create_synthetic_entities(groups: List[dict]) -> List[EntityNode]:
    """Create synthetic EntityNode objects from parsed voter groups."""
    entities = []

    for group in groups:
        # Map group name to entity type
        entity_type = _infer_entity_type(group['name'])

        entity = EntityNode(
            uuid=str(uuid.uuid4()),
            name=group['name'],
            labels=['Entity', entity_type],
            summary=group['description'],
            attributes={
                'percentage': group['percentage'],
                'synthetic': True,
                'group_type': 'voter',
            },
        )
        entities.append(entity)

    return entities


def _infer_entity_type(group_name: str) -> str:
    """Infer an entity type from a group name."""
    name_lower = group_name.lower()

    type_keywords = {
        'PartyVoter': ['wyborc', 'elektorat', 'zwolenni'],
        'YoungVoter': ['młod', 'student', '18-', 'gen z', 'pokolenie'],
        'Journalist': ['dziennikarz', 'media', 'reporter', 'publicyst'],
        'StockInvestor': ['inwestor', 'trader', 'giełd'],
        'Clergy': ['duchow', 'ksiądz', 'księdz', 'kościel', 'kapłan'],
        'Psychologist': ['psycholog', 'terapeut', 'psychiatr'],
        'Teacher': ['nauczyciel', 'pedagog'],
        'Farmer': ['rolnik', 'agricultur'],
        'Programmer': ['programist', 'IT', 'developer'],
        'Politician': ['polityk', 'poseł', 'senator', 'minister'],
        'Activist': ['aktywist', 'działacz'],
    }

    for entity_type, keywords in type_keywords.items():
        for kw in keywords:
            if kw in name_lower:
                return entity_type

    return 'Person'  # Default


def filter_non_actors(entities: List[EntityNode]) -> List[EntityNode]:
    """Remove entities that shouldn't be agents (institutions, concepts, funds)."""
    filtered = []
    removed = []

    for entity in entities:
        entity_type = (entity.get_entity_type() or '').lower()
        name_lower = entity.name.lower()

        # Check if it's a non-actor type
        if entity_type in NON_ACTOR_TYPES:
            removed.append(entity.name)
            continue

        # Check if name matches known non-actors
        if any(na in name_lower for na in NON_ACTOR_NAMES):
            removed.append(entity.name)
            continue

        filtered.append(entity)

    if removed:
        logger.info(f"Filtered out {len(removed)} non-actor entities: {', '.join(removed)}")

    return filtered


def merge_entities_with_groups(
    ner_entities: List[EntityNode],
    requirement: str,
) -> List[EntityNode]:
    """
    Main function: merge NER entities (filtered) with synthetic voter groups.

    1. Filter out non-actor NER entities (CBOS, ZUS, etc.)
    2. Parse voter groups from requirement
    3. Create synthetic entities for groups
    4. Merge: NER persons/parties + synthetic voter groups
    """
    # Step 1: Filter NER entities
    actors = filter_non_actors(ner_entities)

    # Step 2: Parse groups from requirement
    groups = parse_groups_from_requirement(requirement)

    if not groups:
        logger.info("No voter groups found in requirement, using NER entities only")
        return actors

    # Step 3: Create synthetic entities
    synthetic = create_synthetic_entities(groups)

    # Step 4: Merge (NER actors first, then synthetic groups)
    # Avoid duplicates: if NER already has "Donald Tusk" and requirement has "politycy", keep both
    merged = actors + synthetic

    logger.info(f"Merged entity list: {len(actors)} NER actors + {len(synthetic)} voter groups = {len(merged)} total")

    return merged
