import json
import re
import threading
import time

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFProtect

from ..config import LANG_KEY_MAP, LANG_LABELS, SUPPORTED_PROVIDERS
from ..extractors import provider_functions
from ..logger import get_logger
from ..providers import resolve_provider
from ..search import fetch_new_animes, fetch_popular_animes, query_s_to, random_anime
from ..search import query as aniworld_query
from .db import (
    add_to_queue,
    cancel_queue_item,
    clear_completed,
    get_next_queued,
    get_queue,
    get_running,
    init_queue_db,
    is_queue_cancelled,
    move_queue_item,
    remove_from_queue,
    set_queue_status,
    update_queue_errors,
    update_queue_progress,
)

logger = get_logger(__name__)


def _get_working_providers():
    """Return only providers whose extractors are actually implemented."""
    working = []
    for p in SUPPORTED_PROVIDERS:
        func_name = f"get_direct_link_from_{p.lower()}"
        if func_name not in provider_functions:
            continue
        try:
            provider_functions[func_name]("")
        except NotImplementedError:
            continue
        except Exception:
            working.append(p)
    return tuple(working)


WORKING_PROVIDERS = _get_working_providers()

# Only match series-level links: /anime/stream/<slug> (no season/episode)
_SERIES_LINK_PATTERN = re.compile(r"^/anime/stream/[a-zA-Z0-9\-]+/?$", re.IGNORECASE)

# Only match s.to series-level links: /serie/<slug> (no season/episode)
_STO_SERIES_LINK_PATTERN = re.compile(
    r"^/serie/(stream/)?[a-zA-Z0-9\-]+/?$", re.IGNORECASE
)

# Queue worker state
_queue_worker_started = False
_queue_lock = threading.Lock()


def _queue_worker():
    """Single global worker that processes one download at a time."""
    while True:
        try:
            item = None
            with _queue_lock:
                if not get_running():
                    item = get_next_queued()
                    if item:
                        set_queue_status(item["id"], "running")

            if not item:
                time.sleep(3)
                continue

            episodes = json.loads(item["episodes"])
            errors = []

            # Language separation: compute subfolder path if enabled
            import os

            lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
            selected_path = None
            if lang_sep:
                from pathlib import Path

                lang_folder_map = {
                    "German Dub": "german-dub",
                    "English Sub": "english-sub",
                    "German Sub": "german-sub",
                    "English Dub": "english-dub",
                }
                lang_folder = lang_folder_map.get(
                    item["language"], item["language"].lower().replace(" ", "-")
                )
                raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
                if raw:
                    base = Path(raw).expanduser()
                    if not base.is_absolute():
                        base = Path.home() / base
                else:
                    base = Path.home() / "Downloads"
                selected_path = str(base / lang_folder)

            for i, ep_url in enumerate(episodes):
                update_queue_progress(item["id"], i, ep_url)
                try:
                    prov = resolve_provider(ep_url)
                    ep_kwargs = {
                        "url": ep_url,
                        "selected_language": item["language"],
                        "selected_provider": item["provider"],
                    }
                    if selected_path:
                        ep_kwargs["selected_path"] = selected_path
                    episode = prov.episode_cls(**ep_kwargs)
                    episode.download()
                except Exception as e:
                    logger.error(f"Download failed for {ep_url}: {e}")
                    errors.append({"url": ep_url, "error": str(e)})
                    update_queue_errors(item["id"], json.dumps(errors))

                # Check for cancellation after each episode
                if is_queue_cancelled(item["id"]):
                    logger.info(f"Download cancelled for queue item {item['id']}")
                    update_queue_progress(item["id"], i + 1, "")
                    break

            # Only set final status if not already cancelled
            if not is_queue_cancelled(item["id"]):
                update_queue_progress(item["id"], len(episodes), "")
                status = (
                    "failed" if errors and len(errors) == len(episodes) else "completed"
                )
                set_queue_status(item["id"], status)
        except Exception as e:
            logger.error(f"Queue worker error: {e}", exc_info=True)
            time.sleep(3)


def _ensure_queue_worker():
    """Start the queue worker thread once."""
    global _queue_worker_started
    if _queue_worker_started:
        return
    _queue_worker_started = True

    # Crash recovery: reset any 'running' items back to 'queued'
    from .db import get_db

    conn = get_db()
    try:
        conn.execute(
            "UPDATE download_queue SET status = 'queued' WHERE status = 'running'"
        )
        conn.commit()
    finally:
        conn.close()

    thread = threading.Thread(target=_queue_worker, daemon=True)
    thread.start()


def _get_version():
    try:
        from importlib.metadata import version

        return version("aniworld")
    except Exception:
        return ""


def create_app(auth_enabled=False, sso_enabled=False, force_sso=False):
    import os

    app = Flask(__name__)
    app_version = _get_version()

    base_url = os.environ.get("ANIWORLD_WEB_BASE_URL", "").strip().rstrip("/")
    if base_url:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        scheme = parsed.scheme or "https"
        host = parsed.netloc

        # WSGI middleware that overrides scheme/host before Flask sees the request
        _inner_wsgi = app.wsgi_app

        def _proxy_wsgi(environ, start_response):
            environ["wsgi.url_scheme"] = scheme
            if host:
                environ["HTTP_HOST"] = host
            return _inner_wsgi(environ, start_response)

        app.wsgi_app = _proxy_wsgi

    if auth_enabled:
        from .auth import (
            auth_bp,
            get_current_user,
            get_or_create_secret_key,
            init_oidc,
            login_required,
            refresh_session_role,
        )
        from .db import has_any_admin, init_db

        app.secret_key = get_or_create_secret_key()
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        if base_url.startswith("https"):
            app.config["SESSION_COOKIE_SECURE"] = True
        app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours

        csrf = CSRFProtect()

        init_db()
        app.register_blueprint(auth_bp)
        csrf.init_app(app)

        if sso_enabled:
            init_oidc(app, force_sso=force_sso)
        else:
            app.config["OIDC_ENABLED"] = False
            app.config["OIDC_DISPLAY_NAME"] = "SSO"
            app.config["OIDC_ADMIN_USER"] = None
            app.config["OIDC_ADMIN_SUBJECT"] = None
            app.config["FORCE_SSO"] = False

        @app.before_request
        def _check_setup():
            if request.endpoint and request.endpoint.startswith("auth."):
                return None
            if request.endpoint == "static":
                return None
            if not app.config.get("FORCE_SSO", False) and not has_any_admin():
                return redirect(url_for("auth.setup"))
            return None

        @app.before_request
        def _refresh_role():
            return refresh_session_role()

        @app.context_processor
        def _inject_auth():
            return {
                "current_user": get_current_user(),
                "auth_enabled": True,
                "oidc_enabled": app.config.get("OIDC_ENABLED", False),
                "oidc_display_name": app.config.get("OIDC_DISPLAY_NAME", "SSO"),
                "force_sso": app.config.get("FORCE_SSO", False),
                "app_version": app_version,
            }
    else:

        @app.context_processor
        def _inject_no_auth():
            return {
                "current_user": None,
                "auth_enabled": False,
                "oidc_enabled": False,
                "oidc_display_name": "SSO",
                "force_sso": False,
                "app_version": app_version,
            }

    # Initialize download queue (works with or without auth)
    init_queue_db()
    _ensure_queue_worker()

    @app.after_request
    def _set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        return response

    @app.route("/")
    def index():
        sto_lang_labels = {"1": "German Dub", "2": "English Dub"}
        return render_template(
            "index.html",
            lang_labels=LANG_LABELS,
            sto_lang_labels=sto_lang_labels,
            supported_providers=WORKING_PROVIDERS,
        )

    @app.route("/api/search", methods=["POST"])
    def api_search():
        data = request.get_json(silent=True) or {}
        keyword = (data.get("keyword") or "").strip()
        site = (data.get("site") or "aniworld").strip()
        if not keyword:
            return jsonify({"error": "keyword is required"}), 400

        results = []

        if site == "sto":
            # s.to search
            sto_results = query_s_to(keyword) or []
            if isinstance(sto_results, dict):
                sto_results = [sto_results]
            for item in sto_results:
                link = item.get("link", "")
                if _STO_SERIES_LINK_PATTERN.match(link):
                    title = (
                        item.get("title", "Unknown")
                        .replace("<em>", "")
                        .replace("</em>", "")
                    )
                    results.append(
                        {
                            "title": title,
                            "url": f"https://s.to{link}",
                        }
                    )
        else:
            # AniWorld search
            aw_results = aniworld_query(keyword) or []
            if isinstance(aw_results, dict):
                aw_results = [aw_results]
            for item in aw_results:
                link = item.get("link", "")
                if _SERIES_LINK_PATTERN.match(link):
                    title = (
                        item.get("title", "Unknown")
                        .replace("<em>", "")
                        .replace("</em>", "")
                    )
                    results.append(
                        {
                            "title": title,
                            "url": f"https://aniworld.to{link}",
                        }
                    )

        return jsonify({"results": results})

    @app.route("/api/series")
    def api_series():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            series = prov.series_cls(url=url)
            poster = getattr(series, "poster_url", None)
            # s.to returns relative poster paths - make them absolute
            if poster and poster.startswith("/"):
                from urllib.parse import urlparse

                parsed = urlparse(url)
                poster = f"{parsed.scheme}://{parsed.netloc}{poster}"
            return jsonify(
                {
                    "title": series.title,
                    "poster_url": poster,
                    "description": getattr(series, "description", ""),
                    "genres": getattr(series, "genres", []),
                    "release_year": getattr(series, "release_year", ""),
                }
            )
        except Exception as e:
            logger.error(f"Series fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/seasons")
    def api_seasons():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            series = prov.series_cls(url=url)
            seasons_data = []
            for season in series.seasons:
                seasons_data.append(
                    {
                        "url": season.url,
                        "season_number": season.season_number,
                        "episode_count": season.episode_count,
                        "are_movies": getattr(season, "are_movies", False),
                    }
                )
            return jsonify({"seasons": seasons_data})
        except Exception as e:
            logger.error(f"Seasons fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/episodes")
    def api_episodes():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            # Pass series to avoid broken series URL reconstruction in s.to
            # season model (its fallback splits on "-" which fails)
            series_url = re.sub(r"/staffel-\d+/?$", "", url)
            series_url = re.sub(r"/filme/?$", "", series_url)
            try:
                series = prov.series_cls(url=series_url)
            except Exception:
                series = None
            season = prov.season_cls(url=url, series=series)
            episodes_data = []
            for ep in season.episodes:
                episodes_data.append(
                    {
                        "url": ep.url,
                        "episode_number": ep.episode_number,
                        "title_de": getattr(ep, "title_de", ""),
                        "title_en": getattr(ep, "title_en", ""),
                    }
                )
            return jsonify({"episodes": episodes_data})
        except Exception as e:
            logger.error(f"Episodes fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/providers")
    def api_providers():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            episode = prov.episode_cls(url=url)
            pd = episode.provider_data

            disable_eng_sub = os.environ.get("ANIWORLD_DISABLE_ENGLISH_SUB", "0") == "1"
            provider_info = {}

            if hasattr(pd, "_data"):
                # AniWorld: ProviderData object
                lang_tuple_to_label = {}
                for key, (audio, subtitles) in LANG_KEY_MAP.items():
                    label = LANG_LABELS.get(key)
                    if label:
                        lang_tuple_to_label[(audio.value, subtitles.value)] = label

                for (audio, subtitles), providers in pd._data.items():
                    label = lang_tuple_to_label.get((audio.value, subtitles.value))
                    if not label:
                        continue
                    if disable_eng_sub and label == "English Sub":
                        continue
                    working = [p for p in providers.keys() if p in WORKING_PROVIDERS]
                    if working:
                        provider_info[label] = working
            else:
                # s.to: plain dict with (Audio, Subtitles) enum tuple keys
                sto_label_map = {
                    ("German", "None"): "German Dub",
                    ("English", "None"): "English Dub",
                }
                for (audio, subtitles), providers in pd.items():
                    label = sto_label_map.get((audio.value, subtitles.value))
                    if not label:
                        continue
                    working = [p for p in providers.keys() if p in WORKING_PROVIDERS]
                    if working:
                        provider_info[label] = working

            return jsonify({"providers": provider_info})
        except Exception as e:
            logger.error(f"Providers fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/download", methods=["POST"])
    def api_download():
        data = request.get_json(silent=True) or {}
        episodes = data.get("episodes", [])
        language = data.get("language", "German Dub")
        provider = data.get("provider", "VOE")
        title = data.get("title", "Unknown")
        series_url = data.get("series_url", "")

        if not episodes:
            return jsonify({"error": "episodes list is required"}), 400

        if (
            language == "English Sub"
            and os.environ.get("ANIWORLD_DISABLE_ENGLISH_SUB", "0") == "1"
        ):
            return jsonify({"error": "English Sub downloads are disabled"}), 403

        username = None
        if auth_enabled:
            user = get_current_user()
            if user:
                username = (
                    user.get("username")
                    if isinstance(user, dict)
                    else getattr(user, "username", None)
                )

        queue_id = add_to_queue(
            title, series_url, episodes, language, provider, username
        )
        return jsonify({"queue_id": queue_id})

    @app.route("/api/queue")
    def api_queue():
        items = get_queue()
        return jsonify({"items": items})

    @app.route("/api/queue/<int:queue_id>", methods=["DELETE"])
    def api_queue_remove(queue_id):
        ok, err = remove_from_queue(queue_id)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/queue/<int:queue_id>/cancel", methods=["POST"])
    def api_queue_cancel(queue_id):
        ok, err = cancel_queue_item(queue_id)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/queue/<int:queue_id>/move", methods=["POST"])
    def api_queue_move(queue_id):
        data = request.get_json(silent=True) or {}
        direction = data.get("direction", "").strip()
        if direction not in ("up", "down"):
            return jsonify({"error": "direction must be 'up' or 'down'"}), 400
        ok, err = move_queue_item(queue_id, direction)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/queue/completed", methods=["DELETE"])
    def api_queue_clear():
        clear_completed()
        return jsonify({"ok": True})

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/api/random")
    def api_random():
        site = request.args.get("site", "aniworld").strip()
        if site == "sto":
            return jsonify({"error": "Random is not available for S.TO"}), 400
        url = random_anime()
        if url:
            return jsonify({"url": url})
        return jsonify({"error": "Failed to fetch random anime"}), 500

    @app.route("/api/new-animes")
    def api_new_animes():
        results = fetch_new_animes()
        if results is None:
            return jsonify({"error": "Failed to fetch new animes"}), 500
        return jsonify({"results": results})

    @app.route("/api/popular-animes")
    def api_popular_animes():
        results = fetch_popular_animes()
        if results is None:
            return jsonify({"error": "Failed to fetch popular animes"}), 500
        return jsonify({"results": results})

    @app.route("/api/downloaded-folders")
    def api_downloaded_folders():
        from pathlib import Path

        raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
        if raw:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = Path.home() / p
            dl_path = p
        else:
            dl_path = Path.home() / "Downloads"

        folders = set()
        if dl_path.is_dir():
            for entry in dl_path.iterdir():
                if entry.is_dir():
                    folders.add(entry.name)
                    # Also check one level deeper (for language separation subfolders)
                    for child in entry.iterdir():
                        if child.is_dir():
                            folders.add(child.name)
        return jsonify({"folders": sorted(folders)})

    @app.route("/api/settings", methods=["GET"])
    def api_settings():
        from pathlib import Path

        raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
        if raw:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = Path.home() / p
            resolved = str(p)
        else:
            resolved = str(Path.home() / "Downloads")
        lang_separation = os.environ.get("ANIWORLD_LANG_SEPARATION", "0")
        disable_english_sub = os.environ.get("ANIWORLD_DISABLE_ENGLISH_SUB", "0")
        return jsonify(
            {
                "download_path": resolved,
                "lang_separation": lang_separation,
                "disable_english_sub": disable_english_sub,
            }
        )

    @app.route("/api/settings", methods=["PUT"])
    def api_settings_update():
        data = request.get_json(silent=True) or {}
        download_path = data.get("download_path", "").strip()
        os.environ["ANIWORLD_DOWNLOAD_PATH"] = download_path
        if "lang_separation" in data:
            os.environ["ANIWORLD_LANG_SEPARATION"] = (
                "1" if data["lang_separation"] else "0"
            )
        if "disable_english_sub" in data:
            os.environ["ANIWORLD_DISABLE_ENGLISH_SUB"] = (
                "1" if data["disable_english_sub"] else "0"
            )
        return jsonify({"ok": True})

    if auth_enabled:
        from .auth import admin_required

        # Endpoints that require admin instead of just login
        _admin_only = {"settings_page", "api_settings", "api_settings_update"}

        # Wrap all non-auth, non-static view functions with login_required
        # (admin_required for settings endpoints)
        _exempt = {
            "static",
            "auth.login",
            "auth.logout",
            "auth.setup",
            "auth.oidc_login",
            "auth.oidc_callback",
        }
        for endpoint, view_func in list(app.view_functions.items()):
            if endpoint not in _exempt:
                if endpoint in _admin_only:
                    app.view_functions[endpoint] = admin_required(view_func)
                else:
                    app.view_functions[endpoint] = login_required(view_func)

        # Exempt JSON API routes from CSRF (they use Content-Type: application/json
        # which provides implicit cross-origin protection via CORS preflight)
        for endpoint in list(app.view_functions):
            if endpoint.startswith("api_") or endpoint.startswith("auth.admin_"):
                csrf.exempt(app.view_functions[endpoint])

    return app


def start_web_ui(
    host="127.0.0.1",
    port=8080,
    open_browser=True,
    auth_enabled=False,
    sso_enabled=False,
    force_sso=False,
):
    """Start the Flask web UI server."""
    import os
    import threading
    import webbrowser

    # Allow env var overrides (Docker-friendly)
    force_sso = force_sso or os.getenv("ANIWORLD_WEB_FORCE_SSO", "0") == "1"
    sso_enabled = sso_enabled or force_sso or os.getenv("ANIWORLD_WEB_SSO", "0") == "1"
    auth_enabled = (
        auth_enabled or force_sso or os.getenv("ANIWORLD_WEB_AUTH", "0") == "1"
    )

    app = create_app(
        auth_enabled=auth_enabled, sso_enabled=sso_enabled, force_sso=force_sso
    )
    display_host = "localhost" if host == "127.0.0.1" else host
    url = f"http://{display_host}:{port}"
    print(f"Starting AniWorld Web UI on {url}")

    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    debug = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"

    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        from waitress import serve

        serve(app, host=host, port=port)
