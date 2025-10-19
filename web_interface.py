from flask import Flask, render_template_string, request, jsonify
import json
import os
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

CONFIG_FILE = 'monitor_config.json'
STATE_FILE = 'state.json'
EVENTS_CACHE_FILE = 'events_cache.json'
CACHE_DURATION_HOURS = 6

def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'monitored_events': [],
        'purchased_events': [],
        'credentials': {
            'pushover_user_key': '',
            'pushover_app_token': '',
            'gmail_user': '',
            'gmail_app_password': '',
            'notify_email': '',
            'proxy_api_key': ''
        },
        'check_interval_minutes': 45
    }

def save_config(config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_events_cache():
    """Load cached events"""
    if os.path.exists(EVENTS_CACHE_FILE):
        with open(EVENTS_CACHE_FILE, 'r') as f:
            cache = json.load(f)
            cache_time = datetime.fromisoformat(cache.get('timestamp', '2000-01-01'))
            if datetime.now() - cache_time < timedelta(hours=CACHE_DURATION_HOURS):
                return cache.get('events', [])
    return None

def save_events_cache(events):
    """Save events to cache"""
    with open(EVENTS_CACHE_FILE, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'events': events
        }, f, indent=2)

def parse_date(date_string):
    """Parse event date"""
    if not date_string:
        return None
    try:
        formats = ['%A, %B %d, %Y', '%B %d, %Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_string.strip(), fmt)
            except ValueError:
                continue
    except:
        pass
    return None

def fetch_all_events():
    """Fetch all events from SCAD website"""
    # Check cache first
    cached = load_events_cache()
    if cached:
        return cached
    
    try:
        url = 'https://tickets.scadboxoffice.com/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        events = []
        
        event_items = soup.find_all('li', class_='tn-prod-list-item')
        
        for item in event_items:
            try:
                event_season_no = item.get('data-tn-prod-season-no', '')
                
                title_elem = item.find('h4', class_='tn-prod-list-item__property--heading')
                if not title_elem:
                    continue
                title_link = title_elem.find('a')
                if not title_link:
                    continue
                title = title_link.get_text(strip=True)
                
                # Get description if available
                desc_elem = item.find('div', class_='tn-prod-list-item__property--description')
                description = desc_elem.get_text(strip=True)[:200] if desc_elem else ''
                
                # Get image if available
                img_elem = item.find('img')
                image_url = img_elem.get('src', '') if img_elem else ''
                
                perf_items = item.find_all('li', class_='tn-prod-list-item__perf-list-item')
                
                for perf in perf_items:
                    try:
                        perf_no = perf.get('data-tn-performance-no', '')
                        perf_link = perf.find('a', class_='tn-prod-list-item__perf-anchor')
                        if not perf_link:
                            continue
                        
                        perf_url = perf_link.get('href', '')
                        if perf_url and not perf_url.startswith('http'):
                            perf_url = f'https://tickets.scadboxoffice.com{perf_url}'
                        
                        event_id = f"{event_season_no}/{perf_no}"
                        
                        date_elem = perf_link.find('span', class_='tn-prod-list-item__perf-date')
                        time_elem = perf_link.find('span', class_='tn-prod-list-item__perf-time')
                        
                        date_text = date_elem.get_text(strip=True) if date_elem else None
                        time_text = time_elem.get_text(strip=True) if time_elem else None
                        
                        datetime_text = f"{date_text} {time_text}" if date_text and time_text else date_text
                        event_date = parse_date(date_text) if date_text else None
                        
                        status_elem = perf_link.find('span', class_='tn-prod-list-item__perf-status')
                        action_elem = perf_link.find('span', class_='tn-prod-list-item__perf-action')
                        
                        if status_elem and 'Sold Out' in status_elem.get_text():
                            status = 'sold_out'
                        elif action_elem and 'Buy tickets' in action_elem.get_text():
                            status = 'available'
                        else:
                            status = 'unknown'
                        
                        # Skip events that have already passed
                        if event_date and event_date < datetime.now() - timedelta(days=1):
                            continue
                        
                        events.append({
                            'id': event_id,
                            'title': title,
                            'description': description,
                            'image_url': image_url,
                            'url': perf_url,
                            'datetime_text': datetime_text,
                            'date': event_date.isoformat() if event_date else None,
                            'date_text': date_text,
                            'time_text': time_text,
                            'status': status
                        })
                    except Exception as e:
                        continue
                        
            except Exception as e:
                continue
        
        # Sort by date
        events.sort(key=lambda x: x['date'] if x['date'] else '9999')
        
        # Cache the results
        save_events_cache(events)
        
        return events
    except Exception as e:
        print(f"Error fetching events: {e}")
        return []

def check_conflicts(events, monitored_ids, purchased_ids):
    """Check for time conflicts between events"""
    conflicts = []
    
    # Create a map of event_id to event data
    event_map = {e['id']: e for e in events}
    
    all_selected = monitored_ids + purchased_ids
    
    for i, id1 in enumerate(all_selected):
        for id2 in all_selected[i+1:]:
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
                
                # Check if events overlap (within 3 hours of each other)
                time_diff = abs((dt1 - dt2).total_seconds() / 60)
                
                if time_diff < 180:  # 3 hours
                    severity = 'critical' if (id1 in purchased_ids and id2 in purchased_ids) else \
                              'warning' if (id1 in purchased_ids or id2 in purchased_ids) else \
                              'info'
                    
                    conflicts.append({
                        'event1': event1,
                        'event2': event2,
                        'severity': severity,
                        'time_diff_minutes': int(time_diff)
                    })
            except:
                continue
    
    return conflicts

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
            
            <div class="form-group">
                <label>Check Interval (minutes)</label>
                <input type="number" id="check_interval" value="{{ config.check_interval_minutes }}" min="30" max="120">
            </div>
            
            <button class="btn btn-success" onclick="saveSettings()">Save All Settings</button>
        </div>
    </div>
    
    <script>
        let allEvents = [];
        let config = {{ config_json | safe }};
        let currentFilter = 'all';
        let searchTerm = '';
        
        // Load events on page load
        loadEvents();
        
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
                renderEvents();
            } catch (error) {
                document.getElementById('events-loading').innerHTML = 
                    '<p style="color: red;">Error loading events. Please refresh.</p>';
            }
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
            
            return `
                <div class="${cardClass}">
                    ${event.image_url ? `<img src="${event.image_url}" class="event-image" alt="${event.title}">` : ''}
                    <div class="event-content">
                        <div class="event-title">${event.title}</div>
                        <div class="event-datetime">📅 ${event.datetime_text}</div>
                        <div class="event-status ${statusClass}">${statusText}</div>
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
            renderEvents();
        }
        
        function togglePurchased(eventId) {
            const index = config.purchased_events.indexOf(eventId);
            if (index > -1) {
                config.purchased_events.splice(index, 1);
            } else {
                config.purchased_events.push(eventId);
                // Remove from monitored if added to purchased
                const monIndex = config.monitored_events.indexOf(eventId);
                if (monIndex > -1) {
                    config.monitored_events.splice(monIndex, 1);
                }
            }
            saveConfig();
            renderEvents();
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
            
            // Render schedule
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
            saveConfig();
            alert('✅ Settings saved! Restart the monitor for changes to take effect.');
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    config = load_config()
    return render_template_string(
        HTML_TEMPLATE, 
        config=config,
        config_json=json.dumps(config)
    )

@app.route('/api/events')
def get_events():
    refresh = request.args.get('refresh') == 'true'
    
    if refresh:
        # Force refresh by deleting cache
        if os.path.exists(EVENTS_CACHE_FILE):
            os.remove(EVENTS_CACHE_FILE)
    
    events = fetch_all_events()
    return jsonify({'events': events})

@app.route('/api/save-config', methods=['POST'])
def save_config_api():
    config = request.json
    save_config(config)
    
    # Update environment variables for the monitor
    if 'credentials' in config:
        for key, value in config['credentials'].items():
            os.environ[key.upper()] = value
    
    return jsonify({'success': True})

@app.route('/api/conflicts')
def get_conflicts():
    config = load_config()
    events = fetch_all_events()
    
    monitored = config.get('monitored_events', [])
    purchased = config.get('purchased_events', [])
    
    conflicts = check_conflicts(events, monitored, purchased)
    
    return jsonify({
        'conflicts': conflicts,
        'monitored_count': len(monitored),
        'purchased_count': len(purchased)
    })

if __name__ == '__main__':
    print("\n" + "="*70)
    print("SCAD Ticket Monitor Web Interface")
    print("="*70)
    print("\nStarting web interface at: http://localhost:5000")
    print("\nFeatures:")
    print("  • Browse all SCAD film festival events")
    print("  • Select events to monitor for tickets")
    print("  • Mark purchased events")
    print("  • Automatic schedule conflict detection")
    print("\nOpen this URL in your browser to get started.")
    print("Press Ctrl+C to stop the server.")
    print("="*70 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)