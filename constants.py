"""
Application constants for SCAD Ticket Monitor

This module contains all hardcoded values, URLs, file paths, and configuration
constants used throughout the application. Centralizing these values makes the
codebase more maintainable and easier to update.
"""

# URLs
FESTIVAL_URL = 'https://tickets.scadboxoffice.com/'

# File paths
CONFIG_FILE = 'monitor_config.json'
STATE_FILE = 'state.json'
EVENTS_CACHE_FILE = 'events_cache.json'
IMAGE_CACHE_DIR = '/tmp/image_cache'

# API endpoints
PUSHOVER_API_URL = 'https://api.pushover.net/1/messages.json'
GITHUB_API_BASE = 'https://api.github.com'

# Cache settings
CACHE_DURATION_HOURS = 6

# Scraping settings
PAGE_LOAD_TIMEOUT_SECONDS = 20
POST_LOAD_WAIT_SECONDS = 2

# Event assumptions
EVENT_DURATION_MINUTES = 150  # Assume 2.5 hours for conflict detection
PASSED_EVENT_BUFFER_DAYS = 1  # Consider events passed 1 day after date

# CSS selectors (Tessitura platform)
# The SCAD ticketing system uses the Tessitura platform which has consistent class names
SELECTORS = {
    'event_item': 'tn-prod-list-item',
    'event_heading': 'tn-prod-list-item__property--heading',
    'event_description': 'tn-prod-list-item__property--description',
    'performance_item': 'tn-prod-list-item__perf-list-item',
    'performance_anchor': 'tn-prod-list-item__perf-anchor',
    'performance_date': 'tn-prod-list-item__perf-date',
    'performance_time': 'tn-prod-list-item__perf-time',
    'performance_status': 'tn-prod-list-item__perf-status',
    'performance_action': 'tn-prod-list-item__perf-action',
}

# Date formats
DATE_FORMATS = [
    '%A, %B %d, %Y',  # "Saturday, October 25, 2025"
    '%B %d, %Y',      # "October 25, 2025"
]

# HTTP headers
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

# Default configuration structure
DEFAULT_CONFIG = {
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
    'check_interval_minutes': 15,
    'send_test_notifications': False,
    'notify_all_available': False
}

# Notification settings
NOTIFICATION_PRIORITY_NORMAL = 0
NOTIFICATION_PRIORITY_LOW = -1
NOTIFICATION_SOUND = 'pushover'

# Gmail SMTP settings
GMAIL_SMTP_HOST = 'smtp.gmail.com'
GMAIL_SMTP_PORT = 465

# Request timeouts
DEFAULT_TIMEOUT_SECONDS = 10

# Retry settings
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5
