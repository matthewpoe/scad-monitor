"""
Shared Chrome/Selenium utilities for SCAD Ticket Monitor
Used by both web_interface.py and monitor.py
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def get_chrome_driver():
    """
    Create a headless Chrome driver with robust options for containerized environments.
    
    Optimized for Railway deployment with:
    - Low memory footprint (--single-process)
    - Container-safe options (--no-sandbox, --disable-dev-shm-usage)
    - Stealth options to avoid bot detection
    - Automatic cache recovery on failure
    
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    
    Raises:
        Exception: If Chrome driver fails to initialize even after recovery attempt
    """
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
    
    try:
        print("🚀 Starting Chrome WebDriver...")
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Chrome WebDriver started successfully")
        return driver
    except Exception as e:
        print(f"❌ Error creating Chrome driver: {e}")
        
        # Try clearing Selenium cache and retry once
        import shutil
        from pathlib import Path
        
        cache_dir = Path.home() / '.cache' / 'selenium'
        if cache_dir.exists():
            print("🔄 Attempting recovery: clearing cache and retrying...")
            try:
                print(f"🗑️ Clearing ChromeDriver cache at {cache_dir}")
                shutil.rmtree(cache_dir)
                print("✅ Cache cleared successfully")
                
                # Retry once
                print("🚀 Retrying Chrome WebDriver initialization...")
                driver = webdriver.Chrome(options=chrome_options)
                print("✅ Chrome WebDriver started successfully (after cache clear)")
                return driver
            except Exception as retry_error:
                print(f"❌ Retry failed: {retry_error}")
                raise
        else:
            print("ℹ️ No cache directory found to clear")
            raise
