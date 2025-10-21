"""
Date parsing and handling utilities for SCAD Ticket Monitor

This module provides functions for parsing dates from the SCAD website
and checking whether events have passed.
"""

from datetime import datetime, timedelta
from typing import Optional

from constants import DATE_FORMATS, PASSED_EVENT_BUFFER_DAYS


def parse_date(date_string: str) -> Optional[datetime]:
    """
    Parse event date from SCAD format
    
    The SCAD website uses formats like:
    - "Saturday, October 25, 2025" (with day of week)
    - "October 25, 2025" (without day of week)
    
    Args:
        date_string: Date string from SCAD website
        
    Returns:
        datetime object if parsing succeeds, None otherwise
        
    Examples:
        >>> parse_date("Saturday, October 25, 2025")
        datetime.datetime(2025, 10, 25, 0, 0)
        
        >>> parse_date("October 25, 2025")
        datetime.datetime(2025, 10, 25, 0, 0)
        
        >>> parse_date("invalid")
        None
    """
    if not date_string:
        return None

    try:
        # Clean up the string
        date_string = date_string.strip()

        # Try each format
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue

        return None
        
    except Exception as e:
        print(f"Error parsing date '{date_string}': {e}")
        return None


def is_event_passed(event_date: Optional[datetime]) -> bool:
    """
    Check if an event date has passed
    
    Events are considered "passed" if they occurred more than
    PASSED_EVENT_BUFFER_DAYS ago. This buffer prevents events
    from being removed too quickly (e.g., late-night events).
    
    Args:
        event_date: datetime object of the event, or None
        
    Returns:
        True if event has passed, False otherwise
        
    Examples:
        >>> from datetime import datetime, timedelta
        >>> past_date = datetime.now() - timedelta(days=5)
        >>> is_event_passed(past_date)
        True
        
        >>> future_date = datetime.now() + timedelta(days=5)
        >>> is_event_passed(future_date)
        False
        
        >>> is_event_passed(None)
        False
    """
    if not event_date:
        return False

    # Add buffer after the event date
    cutoff = datetime.now() - timedelta(days=PASSED_EVENT_BUFFER_DAYS)
    return event_date < cutoff


def format_datetime_for_display(event_date: Optional[datetime]) -> str:
    """
    Format a datetime for user-friendly display
    
    Args:
        event_date: datetime object to format
        
    Returns:
        Formatted string like "Oct 25, 2025 at 7:00 PM"
        
    Examples:
        >>> dt = datetime(2025, 10, 25, 19, 0)
        >>> format_datetime_for_display(dt)
        'Oct 25, 2025 at 7:00 PM'
    """
    if not event_date:
        return "Date TBD"
    
    return event_date.strftime("%b %d, %Y at %I:%M %p")


def get_time_until_event(event_date: Optional[datetime]) -> Optional[str]:
    """
    Get human-readable time until event
    
    Args:
        event_date: datetime object of the event
        
    Returns:
        String like "in 3 days" or "in 2 hours" or None if date is None
        
    Examples:
        >>> future = datetime.now() + timedelta(days=3, hours=2)
        >>> get_time_until_event(future)
        'in 3 days'
    """
    if not event_date:
        return None
    
    delta = event_date - datetime.now()
    
    if delta.days > 0:
        return f"in {delta.days} day{'s' if delta.days != 1 else ''}"
    
    hours = delta.seconds // 3600
    if hours > 0:
        return f"in {hours} hour{'s' if hours != 1 else ''}"
    
    minutes = delta.seconds // 60
    return f"in {minutes} minute{'s' if minutes != 1 else ''}"
