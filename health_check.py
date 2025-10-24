#!/usr/bin/env python3
"""
Health check script to verify Chrome and Selenium are working properly
Run this before starting the main application
"""

import sys
from chrome_utils import get_chrome_driver


def check_chrome():
    """Verify Chrome and Selenium are working"""
    print("=" * 70)
    print("Chrome/Selenium Health Check")
    print("=" * 70)
    
    try:
        # Try to create a driver
        driver = get_chrome_driver()
        
        # Try to navigate to a simple page
        print("📄 Testing navigation...")
        driver.get("about:blank")
        print("✅ Navigation successful")
        
        # Get Chrome version
        capabilities = driver.capabilities
        chrome_version = capabilities.get('browserVersion', 'unknown')
        print(f"🌐 Chrome version: {chrome_version}")
        
        # Clean up
        driver.quit()
        print("✅ Chrome driver closed properly")
        
        print("=" * 70)
        print("✅ Health check PASSED")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"❌ Health check FAILED: {e}")
        print("=" * 70)
        return False


if __name__ == "__main__":
    success = check_chrome()
    sys.exit(0 if success else 1)
