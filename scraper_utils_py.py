"""
Web scraping utilities for SCAD Ticket Monitor

This module handles fetching and parsing the SCAD Film Festival ticketing
website using Selenium and BeautifulSoup. The SCAD website uses the Tessitura
ticketing platform which has consistent HTML structure.
"""

import time
from typing import List, Dict, Optional, Any
from datetime import datetime

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from chrome_utils import get_chrome_driver
from date_utils import parse_date, is_event_passed
from constants import (
    FESTIVAL_URL,
    PAGE_LOAD_TIMEOUT_SECONDS,
    POST_LOAD_WAIT_SECONDS,
    SELECTORS
)


def fetch_page_html(url: str = FESTIVAL_URL) -> Optional[str]:
    """
    Fetch page HTML using Selenium with Chrome headless browser
    
    Uses Chrome in headless mode to handle JavaScript-rendered content.
    Waits for event items to load before returning HTML.
    
    Args:
        url: URL to fetch (defaults to FESTIVAL_URL)
        
    Returns:
        HTML content as string, or None if fetch fails
        
    Raises:
        Exception: If Chrome driver fails to initialize
    """
    driver = None
    try:
        print(f"Fetching {url} with Selenium...")
        driver = get_chrome_driver()
        driver.get(url)

        # Wait for content to load
        print(f"Waiting up to {PAGE_LOAD_TIMEOUT_SECONDS}s for events to load...")
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT_SECONDS).until(
            EC.presence_of_element_located((By.CLASS_NAME, SELECTORS['event_item']))
        )

        # Allow extra time for images and dynamic content
        print(f"Waiting {POST_LOAD_WAIT_SECONDS}s for additional content...")
        time.sleep(POST_LOAD_WAIT_SECONDS)

        html = driver.page_source
        print(f"✅ Fetched {len(html)} characters of HTML")
        return html

    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None

    finally:
        if driver:
            driver.quit()
            print("Chrome driver closed")


def parse_events_from_html(html: str, skip_passed: bool = True) -> List[Dict[str, Any]]:
    """
    Parse events from SCAD festival page HTML
    
    Extracts information about all film screenings/events including:
    - Title, description, and image
    - Date and time information
    - Ticket availability status
    - URL to purchase tickets
    
    Args:
        html: HTML content from the festival page
        skip_passed: If True, skip events that have already passed
        
    Returns:
        List of event dictionaries with keys:
        - id: Unique event identifier (format: "season_no/perf_no")
        - title: Event title
        - description: Event description (truncated to 200 chars)
        - image_url: URL to event poster/image
        - url: URL to purchase tickets
        - datetime_text: Human-readable date/time string
        - date: ISO format date string
        - date_text: Date portion only
        - time_text: Time portion only
        - status: 'available', 'sold_out', or 'unknown'
        
    Examples:
        >>> html = fetch_page_html()
        >>> events = parse_events_from_html(html)
        >>> len(events) > 0
        True
        >>> 'title' in events[0] and 'status' in events[0]
        True
    """
    if not html:
        print("⚠️ No HTML provided to parse")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    events = []

    # Find all event containers
    event_items = soup.find_all('li', class_=SELECTORS['event_item'])
    print(f"Found {len(event_items)} event items on page")

    if len(event_items) == 0:
        print("⚠️ No event items found!")
        print("First 500 chars of HTML:", html[:500])
        return []

    for item in event_items:
        try:
            # Get the main event season number (used in event ID)
            event_season_no = item.get('data-tn-prod-season-no', '')

            # Extract title
            title_elem = item.find('h4', class_=SELECTORS['event_heading'])
            if not title_elem:
                continue
            title_link = title_elem.find('a')
            if not title_link:
                continue
            title = title_link.get_text(strip=True)

            # Extract description (optional)
            desc_elem = item.find('div', class_=SELECTORS['event_description'])
            description = desc_elem.get_text(strip=True)[:200] if desc_elem else ''

            # Extract image URL
            img_elem = item.find('img')
            image_url = img_elem.get('src', '') if img_elem else ''
            if image_url and not image_url.startswith('http'):
                image_url = f'https://tickets.scadboxoffice.com{image_url}'

            # Find all performances/showtimes for this event
            perf_items = item.find_all('li', class_=SELECTORS['performance_item'])

            for perf in perf_items:
                try:
                    event_data = _parse_performance(
                        perf, 
                        event_season_no, 
                        title, 
                        description, 
                        image_url,
                        skip_passed
                    )
                    
                    if event_data:
                        events.append(event_data)
                        
                except Exception as e:
                    print(f"Error parsing performance: {e}")
                    continue

        except Exception as e:
            print(f"Error parsing event item: {e}")
            continue

    # Sort by date (future events first)
    events.sort(key=lambda x: x['date'] if x['date'] else '9999')
    
    print(f"✅ Successfully parsed {len(events)} events")
    return events


def _parse_performance(
    perf_elem: Any,
    event_season_no: str,
    title: str,
    description: str,
    image_url: str,
    skip_passed: bool
) -> Optional[Dict[str, Any]]:
    """
    Parse a single performance/showtime element
    
    Internal helper function for parse_events_from_html.
    
    Args:
        perf_elem: BeautifulSoup element for the performance
        event_season_no: Season number from parent event
        title: Event title
        description: Event description
        image_url: Event image URL
        skip_passed: Whether to skip passed events
        
    Returns:
        Event dictionary or None if should be skipped
    """
    perf_no = perf_elem.get('data-tn-performance-no', '')
    
    # Find the performance link
    perf_link = perf_elem.find('a', class_=SELECTORS['performance_anchor'])
    if not perf_link:
        return None

    # Get ticket purchase URL
    perf_url = perf_link.get('href', '')
    if perf_url and not perf_url.startswith('http'):
        perf_url = f'https://tickets.scadboxoffice.com{perf_url}'

    # Create unique event ID
    event_id = f"{event_season_no}/{perf_no}"

    # Extract date and time
    date_elem = perf_link.find('span', class_=SELECTORS['performance_date'])
    time_elem = perf_link.find('span', class_=SELECTORS['performance_time'])

    date_text = date_elem.get_text(strip=True) if date_elem else None
    time_text = time_elem.get_text(strip=True) if time_elem else None

    # Combine for display
    datetime_text = f"{date_text} {time_text}" if date_text and time_text else date_text

    # Parse the date
    event_date = parse_date(date_text) if date_text else None

    # Skip passed events if requested
    if skip_passed and is_event_passed(event_date):
        return None

    # Determine availability status
    status = _get_availability_status(perf_link)

    return {
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
    }


def _get_availability_status(perf_link: Any) -> str:
    """
    Determine ticket availability status from performance link element
    
    Args:
        perf_link: BeautifulSoup element for performance link
        
    Returns:
        'available', 'sold_out', or 'unknown'
    """
    status_elem = perf_link.find('span', class_=SELECTORS['performance_status'])
    action_elem = perf_link.find('span', class_=SELECTORS['performance_action'])

    if status_elem and 'Sold Out' in status_elem.get_text():
        return 'sold_out'
    elif action_elem and 'Buy tickets' in action_elem.get_text():
        return 'available'
    else:
        return 'unknown'


def fetch_all_events() -> List[Dict[str, Any]]:
    """
    Fetch and parse all events from SCAD website
    
    Convenience function that combines fetch_page_html and parse_events_from_html.
    
    Returns:
        List of event dictionaries
        
    Examples:
        >>> events = fetch_all_events()
        >>> isinstance(events, list)
        True
    """
    html = fetch_page_html()
    return parse_events_from_html(html) if html else []


def should_monitor_event(event: Dict[str, Any], monitored_events: List[str]) -> bool:
    """
    Check if an event matches monitoring criteria
    
    An event matches if its ID or title contains any of the monitored event
    keywords/IDs (case-insensitive).
    
    Args:
        event: Event dictionary with 'id' and 'title' keys
        monitored_events: List of event IDs or title keywords to monitor
        
    Returns:
        True if event should be monitored
        
    Examples:
        >>> event = {'id': '12345/67890', 'title': 'The Great Film'}
        >>> should_monitor_event(event, ['12345', 'great'])
        True
        >>> should_monitor_event(event, ['other'])
        False
    """
    event_id = event.get('id', '').lower()
    title = event.get('title', '').lower()

    for monitored in monitored_events:
        monitored_lower = monitored.lower()
        if monitored_lower in event_id or monitored_lower in title:
            return True

    return False
