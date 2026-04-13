"""
MiroShark Backend - Flask application factory
"""

import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libraries like transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS
from flask_compress import Compress

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask application factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Set JSON encoding: ensure non-ASCII characters are displayed directly (instead of \uXXXX format)
    # Flask >= 2.3 uses app.json.ensure_ascii, older versions use JSON_AS_ASCII config
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # Set up logging
    logger = setup_logger('miroshark')
    
    # Only print startup info in the reloader subprocess (avoid printing twice in debug mode)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroShark Backend starting...")
        logger.info("=" * 50)
    
    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Enable gzip/brotli response compression
    Compress(app)

    # --- Initialize Neo4jStorage singleton (DI via app.extensions) ---
    from .storage import Neo4jStorage
    try:
        neo4j_storage = Neo4jStorage()
        app.extensions['neo4j_storage'] = neo4j_storage
        if should_log_startup:
            logger.info("Neo4jStorage initialized (connected to %s)", Config.NEO4J_URI)
    except Exception as e:
        logger.error("Neo4jStorage initialization failed: %s", e)
        # Store None so endpoints can return 503 gracefully
        app.extensions['neo4j_storage'] = None

    # --- Initialize Context Layer (political intelligence) ---
    from .context.config import ContextConfig
    if ContextConfig.ENABLED:
        try:
            from .context.storage.qdrant_store import QdrantStore
            from .context.storage.neo4j_political import Neo4jPolitical
            from .context.embedding.embedder import Embedder
            from .context.enrichment.political_enricher import PoliticalEnricher
            from .context.scheduler import ContextScheduler

            redis_client = None
            if ContextConfig.REDIS_URL:
                import redis
                redis_client = redis.from_url(ContextConfig.REDIS_URL, decode_responses=True)

            qdrant = QdrantStore()
            neo4j_pol = Neo4jPolitical(neo4j_storage) if neo4j_storage else None
            embedder = Embedder()
            enricher = PoliticalEnricher(qdrant, neo4j_pol, embedder, redis_client)

            app.extensions['political_enricher'] = enricher

            # Start scheduler (only in reloader subprocess to avoid double-start)
            if neo4j_pol and (not debug_mode or is_reloader_process):
                ctx_scheduler = ContextScheduler(qdrant, neo4j_pol, embedder, redis_client)
                ctx_scheduler.start()
                app.extensions['context_scheduler'] = ctx_scheduler

            if should_log_startup:
                logger.info("Political context layer initialized (Qdrant + Neo4j + scheduler)")
        except Exception as e:
            logger.warning(f"Political context layer failed to initialize: {e}")
            app.extensions['political_enricher'] = None
    else:
        app.extensions['political_enricher'] = None

    # Register simulation process cleanup function (ensure all simulation processes are terminated when server shuts down)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Simulation process cleanup function registered")
    
    # Request logging middleware
    @app.before_request
    def log_request():
        logger = get_logger('miroshark.request')
        logger.debug(f"Request: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Request body: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('miroshark.request')
        logger.debug(f"Response: {response.status_code}")
        return response
    
    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp, templates_bp, settings_bp, observability_bp, context_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(templates_bp, url_prefix='/api/templates')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(observability_bp, url_prefix='/api/observability')
    app.register_blueprint(context_bp, url_prefix='/api/context')
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroShark Backend'}
    
    if should_log_startup:
        logger.info("MiroShark Backend startup complete")
    
    return app

