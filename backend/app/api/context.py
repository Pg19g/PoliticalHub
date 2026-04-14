"""Context Worker admin endpoints — trigger ingestion jobs manually."""

from flask import current_app, jsonify

from . import context_bp


@context_bp.route('/status', methods=['GET'])
def context_status():
    """Get context layer status."""
    enricher = current_app.extensions.get('political_enricher')
    scheduler = current_app.extensions.get('context_scheduler')

    if not enricher:
        return jsonify({'status': 'disabled', 'message': 'Context layer not initialized'}), 200

    qdrant_count = 0
    try:
        qdrant_count = enricher.qdrant.count()
    except Exception:
        pass

    return jsonify({
        'status': 'active',
        'qdrant_articles': qdrant_count,
        'scheduler_running': scheduler is not None,
    })


@context_bp.route('/diagnostics', methods=['GET'])
def context_diagnostics():
    """Detailed diagnostics of all context data."""
    enricher = current_app.extensions.get('political_enricher')
    if not enricher:
        return jsonify({'status': 'disabled'}), 200

    result = {'qdrant': {}, 'neo4j': {}}

    # Qdrant stats
    try:
        result['qdrant']['total_articles'] = enricher.qdrant.count()
    except Exception as e:
        result['qdrant']['error'] = str(e)

    # Neo4j political stats
    try:
        neo4j = enricher.neo4j
        if neo4j:
            with neo4j.storage._driver.session() as session:
                for label in ['Politician', 'Party', 'Bill', 'Committee']:
                    r = session.run(f"MATCH (n:{label}) RETURN count(n) AS cnt")
                    result['neo4j'][label] = r.single()['cnt']
                r = session.run("MATCH ()-[v:VOTED]->() RETURN count(v) AS cnt")
                result['neo4j']['votes'] = r.single()['cnt']
                r = session.run("MATCH ()-[m:MEMBER_OF]->() RETURN count(m) AS cnt")
                result['neo4j']['memberships'] = r.single()['cnt']
                # Sample politicians
                r = session.run("MATCH (p:Politician) RETURN p.name AS name, p.party AS party LIMIT 10")
                result['neo4j']['sample_politicians'] = [dict(rec) for rec in r]
    except Exception as e:
        result['neo4j']['error'] = str(e)

    return jsonify(result)


@context_bp.route('/trigger/rss', methods=['POST'])
def trigger_rss():
    """Manually trigger RSS fetch + embed pipeline."""
    scheduler = current_app.extensions.get('context_scheduler')
    if not scheduler:
        return jsonify({'error': 'Context scheduler not initialized'}), 503

    scheduler.trigger_rss()
    return jsonify({'status': 'ok', 'message': 'RSS fetch + embed triggered'})


@context_bp.route('/trigger/sejm', methods=['POST'])
def trigger_sejm():
    """Manually trigger Sejm API sync."""
    scheduler = current_app.extensions.get('context_scheduler')
    if not scheduler:
        return jsonify({'error': 'Context scheduler not initialized'}), 503

    scheduler.trigger_sejm_sync()
    return jsonify({'status': 'ok', 'message': 'Sejm sync triggered'})


@context_bp.route('/trigger/wiki', methods=['POST'])
def trigger_wiki():
    """Manually trigger Wikipedia politician profiles sync."""
    scheduler = current_app.extensions.get('context_scheduler')
    if not scheduler:
        return jsonify({'error': 'Context scheduler not initialized'}), 503

    scheduler.trigger_wiki_sync()
    return jsonify({'status': 'ok', 'message': 'Wikipedia sync triggered'})
