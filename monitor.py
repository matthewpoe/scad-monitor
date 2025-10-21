"""
SCAD Film Festival Ticket Monitor - Background Worker

This script continuously monitors the SCAD ticketing website for availability
changes and sends notifications via Pushover and/or email when tickets become
available for monitored events.
"""

import time
import random
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Any, Optional

import requests

from config_utils import (
    load_config,
    save_state,
    load_state,
    get_credential
)
from scraper_utils import fetch_all_events, should_monitor_event
from date_utils import is_event_passed
from constants import (
    PUSHOVER_API_URL,
    NOTIFICATION_PRIORITY_NORMAL,
    NOTIFICATION_PRIORITY_LOW,
    NOTIFICATION_SOUND,
    GMAIL_SMTP_HOST,
    GMAIL_SMTP_PORT,
    DEFAULT_TIMEOUT_SECONDS
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TicketMonitor:
    """
    Monitor SCAD Film Festival ticket availability and send notifications

    Attributes:
        config: Configuration dictionary from GitHub Gist
        monitored_events: List of event IDs/keywords to monitor
        previous_states: Dictionary tracking previous ticket status for each event
        event_dates: Dictionary storing parsed dates for events
    """

    def __init__(self):
        """Initialize the ticket monitor with configuration and credentials"""
        # Load configuration from file (created by web interface)
        self.config: Dict[str, Any] = load_config()

        # Get credentials from config or environment variables (fallback)
        self.pushover_user_key: Optional[str] = get_credential(self.config, 'pushover_user_key')
        self.pushover_app_token: Optional[str] = get_credential(self.config, 'pushover_app_token')
        self.gmail_user: Optional[str] = get_credential(self.config, 'gmail_user')
        self.gmail_app_password: Optional[str] = get_credential(self.config, 'gmail_app_password')
        self.notify_email: Optional[str] = get_credential(self.config, 'notify_email')

        # Notification settings
        self.notify_all_available: bool = self.config.get('notify_all_available', False)
        self.send_test_notifications: bool = self.config.get('send_test_notifications', False)

        # Events to monitor (from config file)
        self.monitored_events: List[str] = self.config.get('monitored_events', [])

        # Check interval
        self.check_interval_minutes: int = self.config.get('check_interval_minutes', 45)

        # Store previous states
        self.previous_states: Dict[str, Dict[str, Any]] = {}
        self.event_dates: Dict[str, Any] = {}

        # Load persistent state
        self._load_persistent_state()

    def _load_persistent_state(self) -> None:
        """Load previous states from persistent storage"""
        try:
            state_data = load_state()
            self.previous_states = state_data.get('states', {})
            self.event_dates = state_data.get('dates', {})
            logger.info(f"Loaded {len(self.previous_states)} previous event states")
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            self.previous_states = {}
            self.event_dates = {}

    def _save_persistent_state(self) -> None:
        """Save current states to persistent storage"""
        try:
            state_data = {
                'states': self.previous_states,
                'dates': self.event_dates
            }
            save_state(state_data)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def send_pushover_notification(
            self,
            title: str,
            message: str,
            url: str,
            priority: int = NOTIFICATION_PRIORITY_NORMAL
    ) -> bool:
        """
        Send notification via Pushover

        Args:
            title: Notification title
            message: Notification message body
            url: URL to include in notification
            priority: Pushover priority level (-2 to 2)

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.pushover_user_key or not self.pushover_app_token:
            logger.warning("Pushover not configured (missing user key or app token)")
            return False

        try:
            logger.info(f"Sending Pushover notification: {title}")
            logger.debug(f"User Key: {self.pushover_user_key[:8]}...")
            logger.debug(f"App Token: {self.pushover_app_token[:8]}...")

            response = requests.post(
                PUSHOVER_API_URL,
                data={
                    'token': self.pushover_app_token,
                    'user': self.pushover_user_key,
                    'title': title,
                    'message': message,
                    'url': url,
                    'priority': priority,
                    'sound': NOTIFICATION_SOUND
                },
                timeout=DEFAULT_TIMEOUT_SECONDS
            )

            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response body: {response.text}")

            if response.status_code == 200:
                logger.info("✅ Pushover notification sent successfully")
                return True
            else:
                logger.error(f"Pushover notification failed: {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending Pushover notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Pushover notification: {e}")
            return False

    def send_email_notification(
            self,
            subject: str,
            body: str,
            url: str,
            event_title: str
    ) -> bool:
        """
        Send notification via Gmail

        Args:
            subject: Email subject line
            body: Email body text
            url: URL to include in email
            event_title: Title of the event

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.gmail_user or not self.gmail_app_password or not self.notify_email:
            logger.warning("Email not configured (missing credentials or recipient)")
            return False

        try:
            logger.info(f"Sending email notification to {self.notify_email}")

            msg = MIMEMultipart()
            msg['From'] = self.gmail_user
            msg['To'] = self.notify_email
            msg['Subject'] = subject

            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #4CAF50;">🎬 {subject}</h2>
                    <div style="background-color: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">{event_title}</h3>
                        <p style="font-size: 16px;">{body}</p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{url}" style="background-color: #4CAF50; color: white; padding: 15px 30px; text-decoration: none; display: inline-block; border-radius: 5px; font-size: 18px; font-weight: bold;">Get Tickets Now!</a>
                    </div>
                    <p style="color: #666; font-size: 12px; text-align: center;">
                        Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    </p>
                </body>
            </html>
            """

            msg.attach(MIMEText(html_body, 'html'))

            with smtplib.SMTP_SSL(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=DEFAULT_TIMEOUT_SECONDS) as server:
                server.login(self.gmail_user, self.gmail_app_password)
                server.send_message(msg)

            logger.info("✅ Email notification sent successfully")
            return True

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return False

    def notify(self, event: Dict[str, Any], is_new: bool = True) -> bool:
        """
        Send notifications via both Pushover and email

        Args:
            event: Event dictionary with title, datetime_text, and url
            is_new: Whether tickets just became available (vs still available)

        Returns:
            True if at least one notification was sent successfully
        """
        if is_new:
            title = "SCAD Tickets Available!"
            message = f"{event['title']} ({event['datetime_text']}) - Tickets just became available!"
            priority = NOTIFICATION_PRIORITY_NORMAL
        else:
            title = "SCAD Tickets Still Available"
            message = f"{event['title']} ({event['datetime_text']}) - Tickets are available!"
            priority = NOTIFICATION_PRIORITY_NORMAL

        pushover_sent = self.send_pushover_notification(title, message, event['url'], priority=priority)
        email_sent = self.send_email_notification(title, message, event['url'], event['title'])

        if pushover_sent:
            logger.info("  ✓ Pushover notification sent")
        if email_sent:
            logger.info("  ✓ Email notification sent")

        return pushover_sent or email_sent

    def send_test_notification(self, stats: Dict[str, int]) -> bool:
        """
        Send a test notification with monitoring stats

        Args:
            stats: Dictionary with 'monitored', 'available', 'sold_out', 'passed' counts

        Returns:
            True if notification sent successfully
        """
        logger.info("Sending test notification")
        logger.debug(f"Pushover configured: {bool(self.pushover_user_key and self.pushover_app_token)}")

        title = "🧪 SCAD Monitor Test"
        message = f"""Monitor running successfully!

📊 Stats:
• {stats['monitored']} events monitored
• {stats['available']} currently available
• {stats['sold_out']} sold out
• {stats['passed']} events passed

Last check: {datetime.now().strftime('%I:%M %p')}
Next check in ~{self.check_interval_minutes} min"""

        url = "https://tickets.scadboxoffice.com/"

        pushover_sent = self.send_pushover_notification(
            title,
            message,
            url,
            priority=NOTIFICATION_PRIORITY_LOW
        )

        if pushover_sent:
            logger.info("✅ Test notification sent successfully")
        else:
            logger.error("❌ Test notification failed")

        return pushover_sent

    def reload_config(self) -> None:
        """Reload configuration from GitHub Gist"""
        logger.info("Reloading configuration...")
        self.config = load_config()
        self.monitored_events = self.config.get('monitored_events', [])
        self.notify_all_available = self.config.get('notify_all_available', False)
        self.send_test_notifications = self.config.get('send_test_notifications', False)

        # Reload credentials
        self.pushover_user_key = get_credential(self.config, 'pushover_user_key')
        self.pushover_app_token = get_credential(self.config, 'pushover_app_token')

        logger.info(f"⚙️  Config loaded:")
        logger.info(f"   • Test notifications: {self.send_test_notifications}")
        logger.info(f"   • Notify all available: {self.notify_all_available}")
        logger.info(f"   • Pushover user key: {'✓' if self.pushover_user_key else '✗'}")
        logger.info(f"   • Pushover app token: {'✓' if self.pushover_app_token else '✗'}")

    def monitor(self) -> None:
        """Main monitoring function - checks tickets and sends notifications"""
        logger.info("=" * 70)
        logger.info(f"Check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)

        # Reload config to pick up any changes
        self.reload_config()

        # Parse the festival page
        all_events = fetch_all_events()

        if not all_events:
            logger.warning("No events found (check parsing or connectivity)")
            return

        logger.info(f"Found {len(all_events)} total screenings")

        # Filter to monitored events
        monitored_found = [e for e in all_events if should_monitor_event(e, self.monitored_events)]
        logger.info(f"Monitoring {len(monitored_found)} of your selected events")

        active_count = 0
        passed_count = 0
        available_count = 0
        sold_out_count = 0

        for event in monitored_found:
            event_id = event['id']

            # Check if event has passed
            event_date = datetime.fromisoformat(event['date']) if event.get('date') else None
            if is_event_passed(event_date):
                if event_id not in self.previous_states or not self.previous_states[event_id].get('marked_passed'):
                    logger.info(f"📅 {event['title'][:45]} ({event['datetime_text']})")
                    logger.info(f"   Event passed - removing from monitoring")
                    self.previous_states[event_id] = {'status': 'passed', 'marked_passed': True}
                passed_count += 1
                continue

            active_count += 1
            previous_status = self.previous_states.get(event_id, {}).get('status')
            current_status = event['status']

            logger.info(f"🎬 {event['title'][:45]}")
            logger.info(f"   {event['datetime_text']}")
            logger.info(f"   Status: {current_status} (was: {previous_status})")

            # Track stats
            if current_status == 'available':
                available_count += 1
            elif current_status == 'sold_out':
                sold_out_count += 1

            # Detect status change or notify all available
            if current_status == 'available':
                is_newly_available = previous_status in ['sold_out', 'unknown', None]

                if is_newly_available:
                    logger.info(f"   🎉 TICKETS BECAME AVAILABLE!")
                    self.notify(event, is_new=True)
                elif self.notify_all_available:
                    logger.info(f"   📢 Notifying (still available)")
                    self.notify(event, is_new=False)

            # Update state
            self.previous_states[event_id] = {
                'status': current_status,
                'title': event['title'],
                'datetime': event['datetime_text'],
                'last_checked': datetime.now().isoformat(),
                'marked_passed': False
            }

        self._save_persistent_state()

        logger.info("=" * 70)
        logger.info(
            f"Summary: {active_count} active | {available_count} available | "
            f"{sold_out_count} sold out | {passed_count} passed"
        )
        logger.info("=" * 70)

        # Send test notification if enabled
        if self.send_test_notifications:
            logger.info("🧪 Test notifications enabled - sending test notification...")
            stats = {
                'monitored': active_count,
                'available': available_count,
                'sold_out': sold_out_count,
                'passed': passed_count
            }
            self.send_test_notification(stats)
        else:
            logger.info("💡 Tip: Enable 'Send test notification' in settings to verify Pushover is working")

    def run(self) -> None:
        """Run the monitor continuously in a loop"""
        logger.info("=" * 70)
        logger.info("SCAD Film Festival Ticket Monitor")
        logger.info("=" * 70)
        logger.info(f"Monitoring {len(self.monitored_events)} event(s)")
        logger.info(f"Pushover enabled: {bool(self.pushover_user_key and self.pushover_app_token)}")
        logger.info(f"Email enabled: {bool(self.gmail_user and self.gmail_app_password)}")
        logger.info(f"Notify all available: {self.notify_all_available}")
        logger.info(f"Test notifications: {self.send_test_notifications}")
        logger.info("=" * 70)

        while True:
            try:
                self.monitor()

                # Use configured interval with some randomness to avoid detection
                base_interval = self.check_interval_minutes
                wait_minutes = random.uniform(base_interval - 5, base_interval + 5)
                wait_seconds = wait_minutes * 60

                logger.info(f"💤 Sleeping for {wait_minutes:.1f} minutes...")
                time.sleep(wait_seconds)

            except KeyboardInterrupt:
                logger.info("🛑 Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Error in monitor loop: {e}", exc_info=True)
                logger.info("Waiting 5 minutes before retry...")
                time.sleep(300)


if __name__ == "__main__":
    monitor = TicketMonitor()
    monitor.run()