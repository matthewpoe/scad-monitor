"""
Shared Chrome/Selenium utilities for SCAD Ticket Monitor
Used by both web_interface.py and monitor.py
"""

import os
import shutil
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def clear_chromedriver_cache():
    """
    Clear the Selenium ChromeDriver cache to force fresh download.
    
    This fixes issues where a cached ChromeDriver doesn't match the 
    installed Chrome version, causing exit code -5 crashes.
    """
    cache_dir = os.path.expanduser('~/.cache/selenium')
    if os.path.exists(cache_dir):
        print(f"🗑️  Clearing ChromeDriver cache at {cache_dir}")
        try:
            shutil.rmtree(cache_dir)
            print("✅ Cache cleared successfully")
        except Exception as e:
            print(f"⚠️  Failed to clear cache: {e}")


def get_chrome_version():
    """
    Get the installed Chrome version.
    
    Returns:
        str: Chrome version (e.g., "141.0.7390.122") or None if not found
    """
    try:
        result = subprocess.run(
            ['google-chrome', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        version_str = result.stdout.strip()
        # Extract version number from "Google Chrome 141.0.7390.122"
        version = version_str.split()[-1] if version_str else None
        print(f"📦 Detected Chrome version: {version}")
        return version
    except Exception as e:
        print(f"⚠️  Could not detect Chrome version: {e}")
        return None


def get_chrome_driver():
    """
    Create a headless Chrome driver with robust options for containerized environments.
    
    Optimized for Railway deployment with:
    - Automatic ChromeDriver version matching
    - Cache clearing on startup to prevent version mismatches
    - Low memory footprint (--single-process)
    - Container-safe options (--no-sandbox, --disable-dev-shm-usage)
    - Stealth options to avoid bot detection
    
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    
    Raises:
        Exception: If Chrome driver fails to initialize
    """
    # Check for version mismatch and clear cache if needed
    cache_dir = os.path.expanduser('~/.cache/selenium/chromedriver')
    if os.path.exists(cache_dir):
        print("🔧 Checking ChromeDriver cache for version mismatches...")
        chrome_version = get_chrome_version()
        if chrome_version:
            # List cached versions
            try:
                linux64_dir = os.path.join(cache_dir, 'linux64')
                if os.path.exists(linux64_dir):
                    cached_versions = os.listdir(linux64_dir)
                    print(f"📋 Cached ChromeDriver versions: {cached_versions}")
                    
                    # If versions don't match (first 3 numbers), clear cache
                    chrome_major = '.'.join(chrome_version.split('.')[:3])
                    version_match = any(chrome_major in v for v in cached_versions)
                    
                    if not version_match:
                        print(f"⚠️  Version mismatch! Chrome {chrome_version} vs cached {cached_versions}")
                        clear_chromedriver_cache()
                    else:
                        print(f"✅ ChromeDriver cache matches Chrome version")
            except Exception as e:
                print(f"⚠️  Error checking cache: {e}")
    
    chrome_options = Options()
    
    # Headless mode
    chrome_options.add_argument('--headless=new')  # Use new headless mode
    
    # Security and sandboxing (required for containers)
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-setuid-sandbox')
    
    # GPU and rendering
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    
    # Extensions and automation
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    
    # Window size
    chrome_options.add_argument('--window-size=1920,1080')
    
    # User agent (mimic real browser)
    chrome_options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Container stability options
    chrome_options.add_argument('--disable-dev-tools')
    chrome_options.add_argument('--no-zygote')
    chrome_options.add_argument('--single-process')  # Critical for low-resource containers
    
    # Memory and performance optimization
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--disable-background-timer-throttling')
    chrome_options.add_argument('--disable-backgrounding-occluded-windows')
    chrome_options.add_argument('--disable-breakpad')
    chrome_options.add_argument('--disable-component-extensions-with-background-pages')
    chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
    chrome_options.add_argument('--disable-ipc-flooding-protection')
    chrome_options.add_argument('--disable-renderer-backgrounding')
    chrome_options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
    chrome_options.add_argument('--force-color-profile=srgb')
    chrome_options.add_argument('--hide-scrollbars')
    chrome_options.add_argument('--metrics-recording-only')
    chrome_options.add_argument('--mute-audio')
    
    # Logging (suppress verbose output)
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    
    # Additional stability options for exit code -5 issues
    chrome_options.add_argument('--disable-crash-reporter')
    chrome_options.add_argument('--no-first-run')
    chrome_options.add_argument('--no-default-browser-check')
    chrome_options.add_argument('--disable-translate')
    chrome_options.add_argument('--disable-sync')
    
    try:
        print("🚀 Starting Chrome WebDriver...")
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Chrome WebDriver started successfully")
        return driver
    except Exception as e:
        print(f"❌ Error creating Chrome driver: {e}")
        
        # If driver creation fails, try clearing cache and retry once
        print("🔄 Attempting recovery: clearing cache and retrying...")
        clear_chromedriver_cache()
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            print("✅ Chrome WebDriver started successfully after cache clear")
            return driver
        except Exception as retry_error:
            print(f"❌ Retry failed: {retry_error}")
            raise
