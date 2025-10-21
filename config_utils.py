"""
Configuration and state management utilities for SCAD Ticket Monitor

This module handles loading/saving configuration from GitHub Gist and
managing persistent state in local JSON files.
"""

import json
import os
from typing import Dict, Any, Optional

import requests

from constants import (
    DEFAULT_CONFIG,
    GITHUB_API_BASE,
    CONFIG_FILE,
    STATE_FILE,
    DEFAULT_TIMEOUT_SECONDS
)


def load_config() -> Dict[str, Any]:
    """
    Load configuration from GitHub Gist
    
    Configuration is stored in a GitHub Gist to allow:
    - Persistence across container restarts
    - Easy manual editing if needed
    - Access from both web and worker processes
    
    The Gist should contain a file named 'monitor_config.json' with the
    configuration structure defined in constants.DEFAULT_CONFIG.
    
    Environment variables required:
    - GIST_ID: The GitHub Gist ID
    - GITHUB_TOKEN: A GitHub personal access token with gist scope
    
    Returns:
        Configuration dictionary. Returns DEFAULT_CONFIG if Gist is not
        configured or if loading fails.
        
    Examples:
        >>> config = load_config()
        >>> 'monitored_events' in config
        True
    """
    gist_id = os.getenv('GIST_ID')
    github_token = os.getenv('GITHUB_TOKEN')

    if not gist_id or not github_token:
        print("⚠️ No GIST_ID or GITHUB_TOKEN - using defaults")
        return DEFAULT_CONFIG.copy()

    try:
        print(f"Loading config from GitHub Gist: {gist_id[:8]}...")
        url = f'{GITHUB_API_BASE}/gists/{gist_id}'
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()

        gist_data = response.json()
        config_content = gist_data['files']['monitor_config.json']['content']
        config = json.loads(config_content)

        print("✅ Config loaded from GitHub Gist")
        return config

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error loading config from Gist: {e}")
        return DEFAULT_CONFIG.copy()
    except (KeyError, json.JSONDecodeError) as e:
        print(f"❌ Error parsing config from Gist: {e}")
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        print(f"❌ Unexpected error loading config from Gist: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> bool:
    """
    Save configuration to GitHub Gist
    
    Updates the 'monitor_config.json' file in the configured GitHub Gist
    with the provided configuration.
    
    Args:
        config: Configuration dictionary to save
        
    Returns:
        True if save succeeded, False otherwise
        
    Examples:
        >>> config = load_config()
        >>> config['check_interval_minutes'] = 30
        >>> save_config(config)
        True
    """
    gist_id = os.getenv('GIST_ID')
    github_token = os.getenv('GITHUB_TOKEN')

    if not gist_id or not github_token:
        print("⚠️ No GIST_ID or GITHUB_TOKEN - cannot save config")
        return False

    try:
        print(f"Saving config to GitHub Gist: {gist_id[:8]}...")
        url = f'{GITHUB_API_BASE}/gists/{gist_id}'
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }

        data = {
            'files': {
                'monitor_config.json': {
                    'content': json.dumps(config, indent=2)
                }
            }
        }

        response = requests.patch(url, headers=headers, json=data, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()

        print("✅ Config saved to GitHub Gist")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error saving config to Gist: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error saving config to Gist: {e}")
        return False


def get_state_file_path() -> str:
    """
    Get the appropriate path for state file
    
    Uses /data/state.json if /data directory exists (Railway persistent storage),
    otherwise uses state.json in current directory.
    
    Returns:
        Path to state file
    """
    return f'/data/{STATE_FILE}' if os.path.exists('/data') else STATE_FILE


def load_state() -> Dict[str, Any]:
    """
    Load previous states from file if exists
    
    State includes:
    - states: Dictionary of event_id -> state info (status, last_checked, etc.)
    - dates: Dictionary of event_id -> parsed date info
    
    Returns:
        State dictionary with 'states' and 'dates' keys
        
    Examples:
        >>> state = load_state()
        >>> 'states' in state and 'dates' in state
        True
    """
    state_file = get_state_file_path()
    
    try:
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                return json.load(f)
        return {'states': {}, 'dates': {}}
        
    except json.JSONDecodeError as e:
        print(f"Error parsing state file: {e}")
        return {'states': {}, 'dates': {}}
    except Exception as e:
        print(f"Error loading state: {e}")
        return {'states': {}, 'dates': {}}


def save_state(state_data: Dict[str, Any]) -> bool:
    """
    Save current states to file
    
    Args:
        state_data: Dictionary containing 'states' and 'dates' keys
        
    Returns:
        True if save succeeded, False otherwise
        
    Examples:
        >>> state = load_state()
        >>> state['states']['12345/67890'] = {'status': 'available'}
        >>> save_state(state)
        True
    """
    state_file = get_state_file_path()
    
    try:
        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2)
        return True
        
    except Exception as e:
        print(f"Error saving state: {e}")
        return False


def get_credential(config: Dict[str, Any], key: str) -> Optional[str]:
    """
    Get a credential from config or environment variable (fallback)
    
    Checks config['credentials'][key] first, then falls back to
    environment variable with uppercase name.
    
    Args:
        config: Configuration dictionary
        key: Credential key (e.g., 'pushover_user_key')
        
    Returns:
        Credential value or None if not found
        
    Examples:
        >>> config = load_config()
        >>> get_credential(config, 'pushover_user_key')
        'abc123...'
    """
    creds = config.get('credentials', {})
    return creds.get(key) or os.getenv(key.upper())


def update_env_from_config(config: Dict[str, Any]) -> None:
    """
    Update environment variables from config credentials
    
    Useful after saving config to ensure the monitor process
    picks up new credentials immediately.
    
    Args:
        config: Configuration dictionary with 'credentials' key
    """
    if 'credentials' in config:
        for key, value in config['credentials'].items():
            if value:  # Only set non-empty values
                os.environ[key.upper()] = value
