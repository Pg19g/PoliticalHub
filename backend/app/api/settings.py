"""
Settings API — runtime LLM configuration management.

GET  /api/settings        — return current active config (masked)
POST /api/settings        — update config at runtime (no restart required)
POST /api/settings/test-llm — make a minimal test call and return latency
"""

import time
from flask import request, jsonify

from . import settings_bp
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('miroshark.api.settings')


def _mask_key(key: str) -> str:
    """Return only the last 4 characters of an API key."""
    if not key:
        return ''
    return '****' + key[-4:] if len(key) > 4 else '****'


@settings_bp.route('', methods=['GET'])
def get_settings():
    """Return current active LLM and Neo4j config (API key masked)."""
    return jsonify({
        'success': True,
        'data': {
            'llm': {
                'provider': Config.LLM_PROVIDER,
                'base_url': Config.LLM_BASE_URL,
                'model_name': Config.LLM_MODEL_NAME,
                'api_key_masked': _mask_key(Config.LLM_API_KEY or ''),
                'has_api_key': bool(Config.LLM_API_KEY),
            },
            'neo4j': {
                'uri': Config.NEO4J_URI,
                'user': Config.NEO4J_USER,
            },
        }
    })


@settings_bp.route('', methods=['POST'])
def update_settings():
    """
    Update LLM (and optionally Neo4j) config at runtime.

    Accepted body fields (all optional):
      llm.provider, llm.base_url, llm.model_name, llm.api_key
      neo4j.uri, neo4j.user, neo4j.password
    """
    body = request.get_json(silent=True) or {}

    llm = body.get('llm', {})
    neo4j = body.get('neo4j', {})

    if llm.get('provider'):
        Config.LLM_PROVIDER = llm['provider']
    if llm.get('base_url'):
        Config.LLM_BASE_URL = llm['base_url']
    if llm.get('model_name'):
        Config.LLM_MODEL_NAME = llm['model_name']
    if llm.get('api_key'):
        Config.LLM_API_KEY = llm['api_key']

    if neo4j.get('uri'):
        Config.NEO4J_URI = neo4j['uri']
    if neo4j.get('user'):
        Config.NEO4J_USER = neo4j['user']
    if neo4j.get('password'):
        Config.NEO4J_PASSWORD = neo4j['password']

    logger.info(
        "Settings updated: provider=%s model=%s base_url=%s",
        Config.LLM_PROVIDER, Config.LLM_MODEL_NAME, Config.LLM_BASE_URL
    )

    return jsonify({
        'success': True,
        'data': {
            'llm': {
                'provider': Config.LLM_PROVIDER,
                'base_url': Config.LLM_BASE_URL,
                'model_name': Config.LLM_MODEL_NAME,
                'api_key_masked': _mask_key(Config.LLM_API_KEY or ''),
                'has_api_key': bool(Config.LLM_API_KEY),
            }
        }
    })


@settings_bp.route('/test-llm', methods=['POST'])
def test_llm():
    """
    Make a minimal test call to the current LLM config.
    Returns { success, model, latency_ms, error }.
    """
    try:
        from ..utils.llm_client import LLMClient

        if Config.LLM_PROVIDER == 'claude-code':
            return jsonify({
                'success': True,
                'model': 'claude-code (local CLI)',
                'latency_ms': 0,
                'note': 'claude-code provider does not support connection testing'
            })

        client = LLMClient()
        start = time.time()
        response = client.chat(
            messages=[{'role': 'user', 'content': 'Reply with only the word OK.'}],
            temperature=0,
            max_tokens=8,
        )
        latency_ms = round((time.time() - start) * 1000)

        return jsonify({
            'success': True,
            'model': client.model,
            'latency_ms': latency_ms,
            'response': response.strip()[:100],
        })

    except Exception as e:
        logger.warning("LLM test failed: %s", e)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 200  # Return 200 so the frontend can read the error body
