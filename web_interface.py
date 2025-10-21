"""
SCAD Film Festival Ticket Monitor - Web Interface

Flask web application for browsing events, configuring monitoring,
and managing ticket purchases with schedule conflict detection.
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import requests
from flask import Flask, render_template_string, request, jsonify, send_file

from config_utils import load_config, save_config, update_env_from_config
from scraper_utils import fetch_all_events
from constants import (
    EVENTS_CACHE_FILE,
    CACHE_DURATION_HOURS,
    IMAGE_CACHE_DIR,
    EVENT_DURATION_MINUTES,
    DEFAULT_TIMEOUT_SECONDS
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def load_events_cache() -> Optional[List[Dict[str, Any]]]:
    """
    Load cached events from file

    Returns:
        List of events if cache is valid, None if cache expired or missing
    """
    if not os.path.exists(EVENTS_CACHE_FILE):
        logger.debug("No events cache file found")
        return None

    try:
        with open(EVENTS_CACHE_FILE, 'r') as f:
            cache = json.load(f)
            cache_time = datetime.fromisoformat(cache.get('timestamp', '2000-01-01'))

            if datetime.now() - cache_time < timedelta(hours=CACHE_DURATION_HOURS):
                logger.info(f"Using cached events from {cache_time}")
                return cache.get('events', [])
            else:
                logger.info("Events cache expired")
                return None

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error parsing events cache: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading events cache: {e}")
        return None


def save_events_cache(events: List[Dict[str, Any]]) -> None:
    """
    Save events to cache file

    Args:
        events: List of event dictionaries to cache
    """
    try:
        with open(EVENTS_CACHE_FILE, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'events': events
            }, f, indent=2)
        logger.info(f"Cached {len(events)} events")
    except Exception as e:
        logger.error(f"Error saving events cache: {e}")


def download_and_cache_image(image_url: str) -> Optional[str]:
    """
    Download and cache an image locally

    Args:
        image_url: URL of the image to download

    Returns:
        Local filename if successful, None otherwise
    """
    if not image_url:
        return None

    # Create cache directory
    os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

    # Generate filename from URL hash
    filename = hashlib.md5(image_url.encode()).hexdigest()

    # Determine extension from URL
    if '.jpg' in image_url or '.jpeg' in image_url:
        filename += '.jpg'
    elif '.png' in image_url:
        filename += '.png'
    elif '.gif' in image_url:
        filename += '.gif'
    else:
        filename += '.jpg'  # default

    filepath = os.path.join(IMAGE_CACHE_DIR, filename)

    # If already cached, return the cached filename
    if os.path.exists(filepath):
        logger.debug(f"Image already cached: {filename}")
        return filename

    # Download and cache
    try:
        logger.info(f"Downloading image: {image_url}")
        response = requests.get(
            image_url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )

        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            logger.info(f"Cached image as: {filename}")
            return filename
        else:
            logger.warning(f"Failed to download image: {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading image {image_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error downloading image {image_url}: {e}")
        return None


def fetch_events_with_cache() -> List[Dict[str, Any]]:
    """
    Fetch all events, using cache if available

    Returns:
        List of event dictionaries
    """
    # Check cache first
    cached = load_events_cache()
    if cached:
        logger.info(f"Returning {len(cached)} events from cache")
        return cached

    # Fetch fresh data
    logger.info("Cache miss - fetching fresh events")
    events = fetch_all_events()

    # Cache images and update image URLs
    for event in events:
        if event.get('image_url'):
            original_url = event['image_url']
            cached_filename = download_and_cache_image(original_url)
            if cached_filename:
                event['image_url'] = f'/cached-image/{cached_filename}'

    # Cache the results
    if events:
        save_events_cache(events)

    return events


def check_conflicts(
        events: List[Dict[str, Any]],
        monitored_ids: List[str],
        purchased_ids: List[str]
) -> List[Dict[str, Any]]:
    """
    Check for time conflicts between events

    Args:
        events: List of all event dictionaries
        monitored_ids: List of monitored event IDs
        purchased_ids: List of purchased event IDs

    Returns:
        List of conflict dictionaries with severity levels
    """
    conflicts = []

    # Create a map of event_id to event data
    event_map = {e['id']: e for e in events}

    all_selected = monitored_ids + purchased_ids

    for i, id1 in enumerate(all_selected):
        for id2 in all_selected[i + 1:]:
            event1 = event_map.get(id1)
            event2 = event_map.get(id2)

            if not event1 or not event2:
                continue

            date1 = event1.get('date')
            date2 = event2.get('date')

            if not date1 or not date2:
                continue

            try:
                dt1 = datetime.fromisoformat(date1)
                dt2 = datetime.fromisoformat(date2)

                # Calculate time difference
                time_diff = abs((dt1 - dt2).total_seconds() / 60)

                # Events conflict if within EVENT_DURATION_MINUTES of each other
                if time_diff < EVENT_DURATION_MINUTES:
                    # Determine severity
                    if id1 in purchased_ids and id2 in purchased_ids:
                        severity = 'critical'
                    elif id1 in purchased_ids or id2 in purchased_ids:
                        severity = 'warning'
                    else:
                        severity = 'info'

                    conflicts.append({
                        'event1': event1,
                        'event2': event2,
                        'severity': severity,
                        'time_diff_minutes': int(time_diff)
                    })

            except ValueError as e:
                logger.warning(f"Error parsing dates for conflict check: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error checking conflict: {e}")
                continue

    logger.info(f"Found {len(conflicts)} schedule conflicts")
    return conflicts


@app.route('/cached-image/<filename>')
def serve_cached_image(filename: str):
    """
    Serve a cached image file

    Args:
        filename: Name of the cached image file

    Returns:
        Image file or 404 if not found
    """
    # Security: only allow expected filenames (hash + extension)
    if not filename or '..' in filename or '/' in filename:
        logger.warning(f"Rejected invalid filename: {filename}")
        return '', 404

    filepath = os.path.join(IMAGE_CACHE_DIR, filename)

    if os.path.exists(filepath):
        # Determine mimetype from extension
        if filename.endswith('.png'):
            mimetype = 'image/png'
        elif filename.endswith('.gif'):
            mimetype = 'image/gif'
        else:
            mimetype = 'image/jpeg'

        return send_file(filepath, mimetype=mimetype)

    logger.warning(f"Cached image not found: {filename}")
    return '', 404


@app.route('/')
def index():
    """Render the main web interface"""
    config = load_config()
    return render_template_string(
        HTML_TEMPLATE,
        config=config,
        config_json=json.dumps(config)
    )


@app.route('/api/events')
def get_events():
    """
    API endpoint to get all events

    Query params:
        refresh: If 'true', force refresh from website

    Returns:
        JSON with events list
    """
    refresh = request.args.get('refresh') == 'true'

    if refresh:
        logger.info("Force refresh requested - deleting cache")
        # Force refresh by deleting cache
        if os.path.exists(EVENTS_CACHE_FILE):
            os.remove(EVENTS_CACHE_FILE)

    events = fetch_events_with_cache()
    return jsonify({'events': events})


@app.route('/api/save-config', methods=['POST'])
def save_config_api():
    """
    API endpoint to save configuration

    Expects JSON body with configuration dictionary

    Returns:
        JSON with success status
    """
    try:
        config = request.json

        if not config:
            return jsonify({'success': False, 'error': 'No config provided'}), 400

        success = save_config(config)

        if success:
            # Update environment variables for the monitor
            update_env_from_config(config)
            logger.info("Configuration saved successfully")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save config'}), 500

    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/conflicts')
def get_conflicts():
    """
    API endpoint to get schedule conflicts

    Returns:
        JSON with conflicts list and counts
    """
    try:
        config = load_config()
        events = fetch_events_with_cache()

        monitored = config.get('monitored_events', [])
        purchased = config.get('purchased_events', [])

        conflicts = check_conflicts(events, monitored, purchased)

        return jsonify({
            'conflicts': conflicts,
            'monitored_count': len(monitored),
            'purchased_count': len(purchased)
        })

    except Exception as e:
        logger.error(f"Error getting conflicts: {e}")
        return jsonify({
            'conflicts': [],
            'monitored_count': 0,
            'purchased_count': 0,
            'error': str(e)
        }), 500


# HTML template (keeping the existing template from the original file)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SCAD Ticket Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2em;
            margin-bottom: 10px;
        }

        .tabs {
            display: flex;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }

        .tab {
            flex: 1;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            background: #f8f9fa;
            border: none;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s;
        }

        .tab:hover {
            background: #e9ecef;
        }

        .tab.active {
            background: white;
            color: #667eea;
            border-bottom: 3px solid #667eea;
        }

        .tab-content {
            display: none;
            padding: 30px;
        }

        .tab-content.active {
            display: block;
        }

        .controls {
            display: flex;
            gap: 15px;
            margin-bottom: 25px;
            flex-wrap: wrap;
            align-items: center;
        }

        .search-box {
            flex: 1;
            min-width: 250px;
        }

        .search-box input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 14px;
        }

        .filter-buttons {
            display: flex;
            gap: 10px;
        }

        .filter-btn {
            padding: 10px 20px;
            border: 2px solid #e9ecef;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .filter-btn.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }

        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-success {
            background: #28a745;
            color: white;
        }

        .events-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }

        .event-card {
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            overflow: hidden;
            transition: all 0.3s;
            position: relative;
        }

        .event-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }

        .event-card.monitored {
            border-color: #667eea;
            background: #f8f9ff;
        }

        .event-card.purchased {
            border-color: #28a745;
            background: #f0fff4;
        }

        .event-card.has-conflict {
            position: relative;
        }

        .conflict-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            z-index: 10;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .conflict-badge.critical {
            background: #dc3545;
            color: white;
        }

        .conflict-badge.warning {
            background: #ff6b6b;
            color: white;
        }

        .conflict-badge.info {
            background: #ffc107;
            color: #333;
        }

        .conflict-details-mini {
            font-size: 0.85em;
            color: #dc3545;
            margin-top: 10px;
            padding: 8px;
            background: #fff5f5;
            border-radius: 6px;
            border-left: 3px solid #dc3545;
        }

        .conflict-details-mini.warning {
            color: #ff6b6b;
            background: #fff9f9;
            border-left-color: #ff6b6b;
        }

        .conflict-details-mini.info {
            color: #856404;
            background: #fffef5;
            border-left-color: #ffc107;
        }

        .event-image {
            width: 100%;
            height: 200px;
            object-fit: cover;
            background: #f8f9fa;
        }

        .event-content {
            padding: 20px;
        }

        .event-title {
            font-size: 1.1em;
            font-weight: 600;
            margin-bottom: 10px;
            color: #333;
        }

        .event-datetime {
            color: #6c757d;
            font-size: 0.9em;
            margin-bottom: 10px;
        }

        .event-status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            margin-bottom: 15px;
        }

        .status-available {
            background: #d4edda;
            color: #155724;
        }

        .status-sold-out {
            background: #f8d7da;
            color: #721c24;
        }

        .event-actions {
            display: flex;
            gap: 10px;
        }

        .action-btn {
            flex: 1;
            padding: 10px;
            border: 2px solid #e9ecef;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }

        .action-btn.active {
            border-color: #667eea;
            background: #667eea;
            color: white;
        }

        .action-btn.purchased-btn.active {
            border-color: #28a745;
            background: #28a745;
        }

        .conflicts-section {
            margin-bottom: 30px;
        }

        .conflict-card {
            background: white;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 8px;
        }

        .conflict-card.critical {
            border-left-color: #dc3545;
            background: #fff5f5;
        }

        .conflict-card.warning {
            border-left-color: #ff6b6b;
            background: #fff9f9;
        }

        .conflict-card.info {
            border-left-color: #ffc107;
            background: #fffef5;
        }

        .conflict-icon {
            font-size: 1.2em;
            margin-right: 10px;
        }

        .conflict-details {
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 15px;
            align-items: center;
            margin-top: 10px;
        }

        .conflict-event {
            padding: 10px;
            background: white;
            border-radius: 6px;
        }

        .conflict-time {
            color: #dc3545;
            font-weight: 600;
            text-align: center;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }

        .stat-box {
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border: 2px solid #e9ecef;
        }

        .stat-number {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
        }

        .stat-label {
            color: #6c757d;
            margin-top: 5px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            color: #495057;
            font-weight: 500;
        }

        input[type="text"],
        input[type="email"],
        input[type="password"],
        input[type="number"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 14px;
        }

        input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }

        .help-text {
            font-size: 13px;
            color: #6c757d;
            margin-top: 5px;
        }

        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .alert-info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #6c757d;
        }

        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }

        .section-divider {
            border-top: 2px solid #e9ecef;
            margin: 30px 0;
            padding-top: 30px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @media (max-width: 768px) {
            .events-grid {
                grid-template-columns: 1fr;
            }

            .controls {
                flex-direction: column;
            }

            .search-box {
                min-width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 SCAD Ticket Monitor</h1>
            <p>Select events to monitor and manage your schedule</p>
        </div>

        <div class="tabs">
            <button class="tab active" onclick="switchTab('browse')">Browse Events</button>
            <button class="tab" onclick="switchTab('schedule')">My Schedule</button>
            <button class="tab" onclick="switchTab('settings')">Settings</button>
        </div>

        <div id="browse-tab" class="tab-content active">
            <div class="controls">
                <div class="search-box">
                    <input type="text" id="search" placeholder="Search events..." oninput="filterEvents()">
                </div>
                <div class="filter-buttons">
                    <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">All</button>
                    <button class="filter-btn" data-filter="available" onclick="setFilter('available')">Available</button>
                    <button class="filter-btn" data-filter="sold-out" onclick="setFilter('sold-out')">Sold Out</button>
                    <button class="filter-btn" data-filter="monitored" onclick="setFilter('monitored')">Monitoring</button>
                    <button class="filter-btn" data-filter="purchased" onclick="setFilter('purchased')">Purchased</button>
                </div>
                <button class="btn btn-primary" onclick="refreshEvents()">🔄 Refresh</button>
            </div>

            <div id="events-loading" class="loading">
                <div class="spinner"></div>
                <p>Loading events from SCAD...</p>
            </div>

            <div id="events-container" class="events-grid" style="display: none;"></div>
        </div>

        <div id="schedule-tab" class="tab-content">
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-number" id="stat-monitoring">0</div>
                    <div class="stat-label">Monitoring</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="stat-purchased">0</div>
                    <div class="stat-label">Purchased</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="stat-conflicts">0</div>
                    <div class="stat-label">Conflicts</div>
                </div>
            </div>

            <div class="conflicts-section">
                <h2 style="margin-bottom: 15px;">⚠️ Schedule Conflicts</h2>
                <div id="conflicts-container"></div>
            </div>

            <h2 style="margin-bottom: 15px;">📅 Your Schedule</h2>
            <div id="schedule-container"></div>
        </div>

        <div id="settings-tab" class="tab-content">
            <h2 style="margin-bottom: 20px;">Notification Settings</h2>

            <div class="form-group">
                <label>Pushover User Key</label>
                <input type="text" id="pushover_user_key" value="{{ config.credentials.pushover_user_key }}">
                <p class="help-text">Get from pushover.net dashboard</p>
            </div>

            <div class="form-group">
                <label>Pushover App Token</label>
                <input type="text" id="pushover_app_token" value="{{ config.credentials.pushover_app_token }}">
                <p class="help-text">Create an app at pushover.net/apps</p>
            </div>

            <div class="form-group">
                <label>Gmail Address</label>
                <input type="email" id="gmail_user" value="{{ config.credentials.gmail_user }}">
            </div>

            <div class="form-group">
                <label>Gmail App Password</label>
                <input type="password" id="gmail_app_password" value="{{ config.credentials.gmail_app_password }}">
                <p class="help-text">Generate at myaccount.google.com/apppasswords</p>
            </div>

            <div class="form-group">
                <label>Notification Email</label>
                <input type="email" id="notify_email" value="{{ config.credentials.notify_email }}">
            </div>

            <div class="form-group">
                <label>ScraperAPI Key (Optional)</label>
                <input type="text" id="proxy_api_key" value="{{ config.credentials.proxy_api_key }}">
                <p class="help-text">For IP rotation - get from scraperapi.com</p>
            </div>

            <div class="section-divider"></div>

            <h2 style="margin-bottom: 20px;">🧪 Testing & Notification Options</h2>

            <div class="form-group">
                <label style="display: flex; align-items: center; cursor: pointer;">
                    <input type="checkbox" id="send_test_notifications" {% if config.send_test_notifications %}checked{% endif %} style="width: auto; margin-right: 10px;">
                    <span>Send test notification on every check</span>
                </label>
                <p class="help-text">📤 Get a notification each time the monitor runs with stats. Great for testing! Turn off once you've confirmed notifications are working.</p>
            </div>

            <div class="form-group">
                <label style="display: flex; align-items: center; cursor: pointer;">
                    <input type="checkbox" id="notify_all_available" {% if config.notify_all_available %}checked{% endif %} style="width: auto; margin-right: 10px;">
                    <span>Notify on all available tickets (not just newly available)</span>
                </label>
                <p class="help-text">🔔 Normally you only get notified when tickets become available. Enable this to get notified every check if monitored tickets are available.</p>
            </div>

            <div class="section-divider"></div>

            <h2 style="margin-bottom: 20px;">⏱️ Check Interval</h2>

            <div class="form-group">
                <label>Check Interval (minutes)</label>
                <input type="number" id="check_interval" value="{{ config.check_interval_minutes }}" min="5" max="120">
                <p class="help-text">How often to check for ticket availability (recommended: 15-60 minutes)</p>
            </div>

            <button class="btn btn-success" onclick="saveSettings()">💾 Save All Settings</button>
        </div>
    </div>

    <script>
        let allEvents = [];
        let config = {{ config_json | safe }};
        let currentFilter = 'all';
        let searchTerm = '';
        let allConflicts = [];

        // Load events on page load
        loadEvents();
        loadConflicts();

        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

            event.target.classList.add('active');
            document.getElementById(tabName + '-tab').classList.add('active');

            if (tabName === 'schedule') {
                updateScheduleView();
            }
        }

        async function loadEvents() {
            document.getElementById('events-loading').style.display = 'block';
            document.getElementById('events-container').style.display = 'none';

            try {
                const response = await fetch('/api/events');
                const data = await response.json();
                allEvents = data.events;
                await loadConflicts();
                renderEvents();
            } catch (error) {
                document.getElementById('events-loading').innerHTML = 
                    '<p style="color: red;">Error loading events. Please refresh.</p>';
            }
        }

        async function loadConflicts() {
            try {
                const response = await fetch('/api/conflicts');
                const data = await response.json();
                allConflicts = data.conflicts;
            } catch (error) {
                console.error('Error loading conflicts:', error);
                allConflicts = [];
            }
        }

        function getEventConflicts(eventId) {
            return allConflicts.filter(conflict => 
                conflict.event1.id === eventId || conflict.event2.id === eventId
            );
        }

        async function refreshEvents() {
            await fetch('/api/events?refresh=true');
            await loadEvents();
        }

        function setFilter(filter) {
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filter === filter);
            });
            renderEvents();
        }

        function filterEvents() {
            searchTerm = document.getElementById('search').value.toLowerCase();
            renderEvents();
        }

        function renderEvents() {
            const container = document.getElementById('events-container');
            container.style.display = 'grid';
            document.getElementById('events-loading').style.display = 'none';

            let filtered = allEvents.filter(event => {
                // Search filter
                if (searchTerm && !event.title.toLowerCase().includes(searchTerm)) {
                    return false;
                }

                // Status filter
                const isMonitored = config.monitored_events.includes(event.id);
                const isPurchased = config.purchased_events.includes(event.id);

                if (currentFilter === 'available' && event.status !== 'available') return false;
                if (currentFilter === 'sold-out' && event.status !== 'sold_out') return false;
                if (currentFilter === 'monitored' && !isMonitored) return false;
                if (currentFilter === 'purchased' && !isPurchased) return false;

                return true;
            });

            container.innerHTML = filtered.map(event => createEventCard(event)).join('');
        }

        function createEventCard(event) {
            const isMonitored = config.monitored_events.includes(event.id);
            const isPurchased = config.purchased_events.includes(event.id);

            let cardClass = 'event-card';
            if (isPurchased) cardClass += ' purchased';
            else if (isMonitored) cardClass += ' monitored';

            const statusClass = event.status === 'available' ? 'status-available' : 'status-sold-out';
            const statusText = event.status === 'available' ? '✓ Available' : '✗ Sold Out';

            // Check for conflicts
            const conflicts = getEventConflicts(event.id);
            let conflictBadge = '';
            let conflictDetails = '';

            if (conflicts.length > 0) {
                cardClass += ' has-conflict';

                const purchasedConflicts = conflicts.filter(c => {
                    const otherEvent = c.event1.id === event.id ? c.event2 : c.event1;
                    return config.purchased_events.includes(otherEvent.id);
                });
                const monitoredConflicts = conflicts.filter(c => {
                    const otherEvent = c.event1.id === event.id ? c.event2 : c.event1;
                    return !config.purchased_events.includes(otherEvent.id);
                });

                const highestSeverity = conflicts.reduce((max, c) => {
                    const levels = { 'critical': 3, 'warning': 2, 'info': 1 };
                    return (levels[c.severity] > levels[max]) ? c.severity : max;
                }, 'info');

                const icons = {
                    'critical': '🚨',
                    'warning': '⚠️',
                    'info': 'ℹ️'
                };

                conflictBadge = `<div class="conflict-badge ${highestSeverity}">${icons[highestSeverity]} ${conflicts.length} conflict${conflicts.length > 1 ? 's' : ''}</div>`;

                const purchasedDetails = purchasedConflicts.map(conflict => {
                    const otherEvent = conflict.event1.id === event.id ? conflict.event2 : conflict.event1;
                    return `
                        <div class="conflict-details-mini ${conflict.severity}">
                            <strong>${icons[conflict.severity]} Conflicts with:</strong><br>
                            ${otherEvent.title}<br>
                            <small>${otherEvent.datetime_text} (PURCHASED)</small><br>
                            <small>${conflict.time_diff_minutes} min apart</small>
                        </div>
                    `;
                }).join('');

                let monitoredDetails = '';
                if (monitoredConflicts.length > 0) {
                    if (monitoredConflicts.length <= 2) {
                        monitoredDetails = monitoredConflicts.map(conflict => {
                            const otherEvent = conflict.event1.id === event.id ? conflict.event2 : conflict.event1;
                            return `
                                <div class="conflict-details-mini info">
                                    <strong>ℹ️ Conflicts with:</strong><br>
                                    ${otherEvent.title}<br>
                                    <small>${otherEvent.datetime_text} (Monitored)</small><br>
                                    <small>${conflict.time_diff_minutes} min apart</small>
                                </div>
                            `;
                        }).join('');
                    } else {
                        const titles = monitoredConflicts.map(c => {
                            const otherEvent = c.event1.id === event.id ? c.event2 : c.event1;
                            return otherEvent.title;
                        }).join(', ');
                        monitoredDetails = `
                            <div class="conflict-details-mini info">
                                <strong>ℹ️ ${monitoredConflicts.length} monitored conflicts:</strong><br>
                                <small>${titles}</small>
                            </div>
                        `;
                    }
                }

                conflictDetails = purchasedDetails + monitoredDetails;
            }

            return `
                <div class="${cardClass}">
                    ${conflictBadge}
                    ${event.image_url ? `<img src="${event.image_url}" class="event-image" alt="${event.title}">` : ''}
                    <div class="event-content">
                        <div class="event-title">${event.title}</div>
                        <div class="event-datetime">📅 ${event.datetime_text}</div>
                        <div class="event-status ${statusClass}">${statusText}</div>
                        ${conflictDetails}
                        <div class="event-actions">
                            <button class="action-btn ${isMonitored ? 'active' : ''}" 
                                    onclick="toggleMonitor('${event.id}')" 
                                    ${isPurchased ? 'disabled' : ''}>
                                ${isMonitored ? '👁️ Monitoring' : '👁️ Monitor'}
                            </button>
                            <button class="action-btn purchased-btn ${isPurchased ? 'active' : ''}" 
                                    onclick="togglePurchased('${event.id}')">
                                ${isPurchased ? '✓ Purchased' : '🎫 Purchased?'}
                            </button>
                            ${event.url ? `
                            <a href="${event.url}" target="_blank" class="action-btn" style="text-decoration: none; display: block; text-align: center;">
                                🎟️ Get Tickets
                            </a>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        }

        function toggleMonitor(eventId) {
            const index = config.monitored_events.indexOf(eventId);
            if (index > -1) {
                config.monitored_events.splice(index, 1);
            } else {
                if (!config.purchased_events.includes(eventId)) {
                    config.monitored_events.push(eventId);
                }
            }
            saveConfig();
            loadConflicts().then(() => renderEvents());
        }

        function togglePurchased(eventId) {
            const index = config.purchased_events.indexOf(eventId);
            if (index > -1) {
                config.purchased_events.splice(index, 1);
            } else {
                config.purchased_events.push(eventId);
                const monIndex = config.monitored_events.indexOf(eventId);
                if (monIndex > -1) {
                    config.monitored_events.splice(monIndex, 1);
                }
            }
            saveConfig();
            loadConflicts().then(() => renderEvents());
        }

        async function updateScheduleView() {
            const response = await fetch('/api/conflicts');
            const data = await response.json();

            document.getElementById('stat-monitoring').textContent = config.monitored_events.length;
            document.getElementById('stat-purchased').textContent = config.purchased_events.length;
            document.getElementById('stat-conflicts').textContent = data.conflicts.length;

            const conflictsContainer = document.getElementById('conflicts-container');
            if (data.conflicts.length === 0) {
                conflictsContainer.innerHTML = '<div class="alert alert-info">✨ No scheduling conflicts detected!</div>';
            } else {
                conflictsContainer.innerHTML = data.conflicts.map(conflict => {
                    const icons = {
                        'critical': '🚨',
                        'warning': '⚠️',
                        'info': 'ℹ️'
                    };

                    const messages = {
                        'critical': 'CRITICAL: Both events are purchased!',
                        'warning': 'WARNING: Conflict with purchased event',
                        'info': 'Potential conflict in wishlist'
                    };

                    return `
                        <div class="conflict-card ${conflict.severity}">
                            <div>
                                <span class="conflict-icon">${icons[conflict.severity]}</span>
                                <strong>${messages[conflict.severity]}</strong>
                                <span style="color: #6c757d; margin-left: 10px;">
                                    ${conflict.time_diff_minutes} minutes apart
                                </span>
                            </div>
                            <div class="conflict-details">
                                <div class="conflict-event">
                                    <strong>${conflict.event1.title}</strong>
                                    <div style="font-size: 0.9em; color: #6c757d; margin-top: 5px;">
                                        ${conflict.event1.datetime_text}
                                    </div>
                                </div>
                                <div class="conflict-time">
                                    ⚡
                                </div>
                                <div class="conflict-event">
                                    <strong>${conflict.event2.title}</strong>
                                    <div style="font-size: 0.9em; color: #6c757d; margin-top: 5px;">
                                        ${conflict.event2.datetime_text}
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            const scheduleContainer = document.getElementById('schedule-container');
            const allScheduled = [
                ...config.purchased_events.map(id => ({id, type: 'purchased'})),
                ...config.monitored_events.map(id => ({id, type: 'monitored'}))
            ];

            if (allScheduled.length === 0) {
                scheduleContainer.innerHTML = '<div class="alert alert-info">No events selected yet. Go to Browse Events to add some!</div>';
            } else {
                const eventMap = {};
                allEvents.forEach(e => eventMap[e.id] = e);

                scheduleContainer.innerHTML = '<div class="events-grid">' + 
                    allScheduled
                        .map(item => eventMap[item.id])
                        .filter(e => e)
                        .sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999'))
                        .map(event => createEventCard(event))
                        .join('') +
                    '</div>';
            }
        }

        function saveConfig() {
            fetch('/api/save-config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });
        }

        function saveSettings() {
            config.credentials = {
                pushover_user_key: document.getElementById('pushover_user_key').value,
                pushover_app_token: document.getElementById('pushover_app_token').value,
                gmail_user: document.getElementById('gmail_user').value,
                gmail_app_password: document.getElementById('gmail_app_password').value,
                notify_email: document.getElementById('notify_email').value,
                proxy_api_key: document.getElementById('proxy_api_key').value
            };
            config.check_interval_minutes = parseInt(document.getElementById('check_interval').value);
            config.send_test_notifications = document.getElementById('send_test_notifications').checked;
            config.notify_all_available = document.getElementById('notify_all_available').checked;

            saveConfig();
            alert('✅ Settings saved! The monitor will pick up changes on the next check cycle.');
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    logger.info("=" * 70)
    logger.info("SCAD Ticket Monitor Web Interface")
    logger.info("=" * 70)
    logger.info("\nStarting web interface...")
    logger.info("\nFeatures:")
    logger.info("  • Browse all SCAD film festival events")
    logger.info("  • Select events to monitor for tickets")
    logger.info("  • Mark purchased events")
    logger.info("  • Automatic schedule conflict detection")
    logger.info("  • Test notifications")
    logger.info("\nPress Ctrl+C to stop the server.")
    logger.info("=" * 70 + "\n")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)