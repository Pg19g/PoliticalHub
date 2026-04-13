"""Client for the Polish Sejm public API (api.sejm.gov.pl)."""

import logging
from typing import List, Dict, Any

import requests

from ..config import ContextConfig

logger = logging.getLogger('miroshark.context.sejm')


class SejmClient:
    """Fetches data from the Polish parliament API."""

    def __init__(self):
        self.base = f"{ContextConfig.SEJM_BASE_URL}/sejm/term{ContextConfig.SEJM_TERM}"
        self.timeout = 30

    def _get(self, path: str) -> Any:
        """HTTP GET with error handling."""
        url = f"{self.base}{path}"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_mps(self) -> List[Dict[str, Any]]:
        """Fetch all MPs for the current term."""
        raw = self._get('/MP')
        mps = []
        for mp in raw:
            mps.append({
                'sejm_id': mp['id'],
                'name': f"{mp.get('firstName', '')} {mp.get('lastName', '')}".strip(),
                'party': mp.get('club', ''),
                'role': mp.get('profession', ''),
                'district': mp.get('districtName', ''),
                'photo_url': f"{self.base}/MP/{mp['id']}/photo",
            })
        logger.info(f"Fetched {len(mps)} MPs from Sejm API")
        return mps

    def get_committees(self) -> List[Dict[str, Any]]:
        """Fetch all parliamentary committees."""
        raw = self._get('/committees')
        committees = []
        for c in raw:
            committees.append({
                'name': c.get('name', ''),
                'code': c.get('code', ''),
                'type': c.get('type', 'standing'),
            })
        logger.info(f"Fetched {len(committees)} committees")
        return committees

    def get_committee_members(self, code: str) -> List[int]:
        """Fetch MP IDs for a committee."""
        try:
            raw = self._get(f'/committees/{code}/members')
            return [m['id'] for m in raw if 'id' in m]
        except Exception as e:
            logger.warning(f"Committee members fetch failed ({code}): {e}")
            return []

    def get_recent_votings(self, sitting: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch votings for a sitting."""
        try:
            raw = self._get(f'/votings/{sitting}')
            votings = []
            for v in raw[:limit]:
                votings.append({
                    'sitting': sitting,
                    'number': v.get('votingNumber', 0),
                    'title': v.get('topic', ''),
                    'date': v.get('date', ''),
                    'yes': v.get('yes', 0),
                    'no': v.get('no', 0),
                    'abstain': v.get('abstain', 0),
                })
            return votings
        except Exception as e:
            logger.warning(f"Votings fetch failed (sitting {sitting}): {e}")
            return []

    def get_voting_details(self, sitting: int, number: int) -> List[Dict[str, Any]]:
        """Fetch individual MP votes for a specific voting."""
        try:
            raw = self._get(f'/votings/{sitting}/{number}')
            votes = []
            for v in raw.get('votes', []):
                votes.append({
                    'sejm_id': v.get('MP', 0),
                    'vote': v.get('vote', ''),
                })
            return votes
        except Exception as e:
            logger.warning(f"Voting details fetch failed ({sitting}/{number}): {e}")
            return []

    def get_prints(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent legislative prints (bills)."""
        try:
            raw = self._get('/prints')
            sorted_prints = sorted(raw, key=lambda x: x.get('number', ''), reverse=True)[:limit]
            bills = []
            for p in sorted_prints:
                bills.append({
                    'number': p.get('number', ''),
                    'title': p.get('title', ''),
                    'category': p.get('documentType', ''),
                    'status': 'active',
                    'date': p.get('documentDate', ''),
                })
            logger.info(f"Fetched {len(bills)} recent prints")
            return bills
        except Exception as e:
            logger.warning(f"Prints fetch failed: {e}")
            return []
