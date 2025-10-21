# SCAD Ticket Monitor - Quick Reference

## Import Cheat Sheet

### Need to work with dates?
```python
from date_utils import parse_date, is_event_passed
```

### Need to load/save config?
```python
from config_utils import load_config, save_config, get_credential
```

### Need to scrape events?
```python
from scraper_utils import fetch_all_events, should_monitor_event
```

### Need Chrome driver?
```python
from chrome_utils import get_chrome_driver
```

### Need constants?
```python
from constants import FESTIVAL_URL, SELECTORS, DEFAULT_CONFIG
```

## Common Patterns

### Pattern: Fetch and Filter Events
```python
from scraper_utils import fetch_all_events, should_monitor_event
from config_utils import load_config

config = load_config()
all_events = fetch_all_events()
monitored = [e for e in all_events if should_monitor_event(e, config['monitored_events'])]
```

### Pattern: Check Event Status
```python
from date_utils import parse_date, is_event_passed

event_date = parse_date(event['date_text'])
if is_event_passed(event_date):
    print("Event has passed")
```

### Pattern: Load Config with Credentials
```python
from config_utils import load_config, get_credential

config = load_config()
pushover_key = get_credential(config, 'pushover_user_key')
```

### Pattern: Save State
```python
from config_utils import load_state, save_state

state = load_state()
state['states']['event_123'] = {'status': 'available'}
save_state(state)
```

### Pattern: Scrape with Chrome
```python
from chrome_utils import get_chrome_driver

driver = get_chrome_driver()
driver.get('https://example.com')
# ... do something ...
driver.quit()
```

## Module Responsibilities

| Module | Responsibility | Size |
|--------|---------------|------|
| `constants.py` | Configuration, URLs, defaults | ~150 lines |
| `date_utils.py` | Date parsing and checking | ~100 lines |
| `config_utils.py` | Config/state persistence | ~200 lines |
| `scraper_utils.py` | Web scraping and parsing | ~250 lines |
| `chrome_utils.py` | Chrome driver setup | ~100 lines |
| `monitor.py` | Background monitoring loop | ~350 lines |
| `web_interface.py` | Flask web UI | ~600 lines |

## Logging Levels

```python
import logging

# Set in each module:
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Usage:
logger.debug("Detailed info for debugging")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)  # Include stack trace
```

## Type Hints Quick Guide

```python
from typing import Dict, List, Optional, Any

def my_function(
    param1: str,                    # Required string
    param2: int = 5,                # Optional int with default
    param3: Optional[str] = None,   # Optional string, defaults to None
    param4: List[str] = None,       # List of strings
    param5: Dict[str, Any] = None   # Dictionary with string keys
) -> bool:                          # Returns boolean
    """Function docstring"""
    return True
```

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GIST_ID` | Yes | GitHub Gist ID for config storage |
| `GITHUB_TOKEN` | Yes | GitHub token for Gist access |
| `PORT` | No (auto) | Port for web service (Railway sets this) |
| `PUSHOVER_USER_KEY` | No | Pushover user key (fallback if not in config) |
| `PUSHOVER_APP_TOKEN` | No | Pushover app token (fallback if not in config) |

## Constants Quick Reference

### URLs
```python
FESTIVAL_URL = 'https://tickets.scadboxoffice.com/'
PUSHOVER_API_URL = 'https://api.pushover.net/1/messages.json'
```

### File Paths
```python
CONFIG_FILE = 'monitor_config.json'
STATE_FILE = 'state.json'
EVENTS_CACHE_FILE = 'events_cache.json'
IMAGE_CACHE_DIR = '/tmp/image_cache'
```

### Timing
```python
CACHE_DURATION_HOURS = 6
PAGE_LOAD_TIMEOUT_SECONDS = 20
POST_LOAD_WAIT_SECONDS = 2
EVENT_DURATION_MINUTES = 150
PASSED_EVENT_BUFFER_DAYS = 1
```

### CSS Selectors
```python
SELECTORS = {
    'event_item': 'tn-prod-list-item',
    'event_heading': 'tn-prod-list-item__property--heading',
    'performance_anchor': 'tn-prod-list-item__perf-anchor',
    # ... etc
}
```

## Common Tasks

### Task: Add a new notification method

1. Add credentials to `constants.py` DEFAULT_CONFIG
2. Add send function to `monitor.py` TicketMonitor class
3. Call from `notify()` method
4. Add UI fields to `web_interface.py` HTML_TEMPLATE

### Task: Support a new ticketing site

1. Add URL to `constants.py`
2. Add CSS selectors to `constants.py` SELECTORS
3. Update `scraper_utils.py` parsing logic if needed
4. Create site-specific parser if structure is very different

### Task: Change check interval

Update in web UI Settings tab, or directly in GitHub Gist:
```json
{
  "check_interval_minutes": 30
}
```

### Task: Debug why events aren't loading

1. Check Railway logs for errors
2. Verify Chrome is working: look for "Chrome driver closed" in logs
3. Check if HTML structure changed: inspect SELECTORS in constants.py
4. Test locally with logging.DEBUG level

## File Size Reference

Original structure:
- `monitor.py`: ~450 lines (with duplicates)
- `web_interface.py`: ~700 lines (with duplicates)
- **Total: ~1150 lines**

Refactored structure:
- Utility modules: ~800 lines
- `monitor.py`: ~350 lines (cleaner)
- `web_interface.py`: ~600 lines (cleaner)
- **Total: ~1750 lines** (includes documentation and type hints)

**Result:** More code, but much better organized and maintainable!

## Troubleshooting

### Import Error
```
ModuleNotFoundError: No module named 'constants'
```
→ Ensure all `.py` files are in the same directory

### Logging Not Showing
```python
# Add to top of file:
import logging
logging.basicConfig(level=logging.INFO, force=True)
```

### Type Errors
→ Type hints don't affect runtime. Use `mypy` for checking during development

### Configuration Not Updating
→ Monitor reloads config on each check cycle. Wait for next check or restart worker

### Chrome Crashes
→ Check Railway memory usage. Chrome needs ~200MB RAM minimum
