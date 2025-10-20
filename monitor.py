import requests
from bs4 import BeautifulSoup
import time
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timedelta
import json
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class TicketMonitor:
    def __init__(self):
        # Load configuration from file (created by web interface)
        self.config = self.load_config()

        # Get credentials from config or environment variables (fallback)
        creds = self.config.get('credentials', {})
        self.pushover_user_key = creds.get('pushover_user_key') or os.getenv('PUSHOVER_USER_KEY')
        self.pushover_app_token = creds.get('pushover_app_token') or os.getenv('PUSHOVER_APP_TOKEN')
        self.gmail_user = creds.get('gmail_user') or os.getenv('GMAIL_USER')
        self.gmail_app_password = creds.get('gmail_app_password') or os.getenv('GMAIL_APP_PASSWORD')
        self.notify_email = creds.get('notify_email') or os.getenv('NOTIFY_EMAIL')
        self.proxy_api_key = creds.get('proxy_api_key') or os.getenv('PROXY_API_KEY')

        # New notification settings
        self.notify_all_available = self.config.get('notify_all_available', False)
        self.send_test_notifications = self.config.get('send_test_notifications', False)

        # Main festival page URL
        self.festival_url = 'https://tickets.scadboxoffice.com/'

        # Events to monitor (from config file)
        self.monitored_events = self.config.get('monitored_events', [])

        # Check interval
        self.check_interval_minutes = self.config.get('check_interval_minutes', 45)

        # Store previous states
        self.previous_states = {}
        self.event_dates = {}
        self.load_state()

    def load_config(self):
        """Load configuration from GitHub Gist"""
        gist_id = os.getenv('GIST_ID')
        github_token = os.getenv('GITHUB_TOKEN')

        if not gist_id or not github_token:
            print("⚠️ No GIST_ID or GITHUB_TOKEN - using defaults")
            return {
                'monitored_events': [],
                'credentials': {},
                'check_interval_minutes': 15,
                'notify_all_available': False,
                'send_test_notifications': False
            }

        try:
            print(f"Loading config from GitHub Gist...")
            url = f'https://api.github.com/gists/{gist_id}'
            headers = {
                'Authorization': f'token {github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            gist_data = response.json()
            config_content = gist_data['files']['monitor_config.json']['content']
            config = json.loads(config_content)

            print("✅ Config loaded from GitHub Gist")
            return config

        except Exception as e:
            print(f"❌ Error loading config from Gist: {e}")
            return {
                'monitored_events': [],
                'credentials': {},
                'check_interval_minutes': 15,
                'notify_all_available': False,
                'send_test_notifications': False
            }

    def load_state(self):
        """Load previous states from file if exists"""
        state_file = '/data/state.json' if os.path.exists('/data') else 'state.json'
        try:
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    data = json.load(f)
                    self.previous_states = data.get('states', {})
                    self.event_dates = data.get('dates', {})
        except Exception as e:
            print(f"Error loading state: {e}")
            self.previous_states = {}
            self.event_dates = {}

    def save_state(self):
        """Save current states to file"""
        state_file = '/data/state.json' if os.path.exists('/data') else 'state.json'
        try:
            with open(state_file, 'w') as f:
                json.dump({
                    'states': self.previous_states,
                    'dates': self.event_dates
                }, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")

    def get_random_headers(self):
        """Generate realistic browser headers"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]

        return {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }

    def get_chrome_driver(self):
        """Create a headless Chrome driver"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        return webdriver.Chrome(options=chrome_options)

    def fetch_page(self, url):
        """Fetch page with Selenium"""
        driver = None
        try:
            print(f"Fetching {url} with Selenium...")
            driver = self.get_chrome_driver()
            driver.get(url)

            # Wait for content
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "tn-prod-list-item"))
            )

            import time
            time.sleep(2)

            html = driver.page_source
            return html

        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

        finally:
            if driver:
                driver.quit()

    def parse_date(self, date_string):
        """Parse event date from SCAD format"""
        if not date_string:
            return None

        try:
            # Format: "Saturday, October 25, 2025" or "October 25, 2025"
            # Clean up the string
            date_string = date_string.strip()

            # Try with day of week first
            formats = [
                '%A, %B %d, %Y',  # "Saturday, October 25, 2025"
                '%B %d, %Y',  # "October 25, 2025"
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_string, fmt)
                except ValueError:
                    continue

            return None
        except Exception as e:
            print(f"Error parsing date '{date_string}': {e}")
            return None

    def is_event_passed(self, event_date):
        """Check if an event date has passed"""
        if not event_date:
            return False

        # Add a 1-day buffer after the event date
        cutoff = datetime.now() - timedelta(days=1)
        return event_date < cutoff

    def parse_festival_page(self):
        """Parse the SCAD festival page and extract event information"""
        html = self.fetch_page(self.festival_url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        events = []

        # Find all event list items
        event_items = soup.find_all('li', class_='tn-prod-list-item')

        for item in event_items:
            try:
                # Get the main event season number (event ID)
                event_season_no = item.get('data-tn-prod-season-no', '')

                # Get the event title
                title_elem = item.find('h4', class_='tn-prod-list-item__property--heading')
                if not title_elem:
                    continue
                title_link = title_elem.find('a')
                if not title_link:
                    continue
                title = title_link.get_text(strip=True)

                # Get the main event URL
                main_event_url = title_link.get('href', '')
                if main_event_url and not main_event_url.startswith('http'):
                    main_event_url = f'https://tickets.scadboxoffice.com{main_event_url}'

                # Find all performances for this event
                perf_items = item.find_all('li', class_='tn-prod-list-item__perf-list-item')

                for perf in perf_items:
                    try:
                        perf_no = perf.get('data-tn-performance-no', '')

                        # Get the performance link
                        perf_link = perf.find('a', class_='tn-prod-list-item__perf-anchor')
                        if not perf_link:
                            continue

                        perf_url = perf_link.get('href', '')
                        if perf_url and not perf_url.startswith('http'):
                            perf_url = f'https://tickets.scadboxoffice.com{perf_url}'

                        # Create a unique ID combining season and performance number
                        event_id = f"{event_season_no}/{perf_no}"

                        # Get date and time
                        date_elem = perf_link.find('span', class_='tn-prod-list-item__perf-date')
                        time_elem = perf_link.find('span', class_='tn-prod-list-item__perf-time')

                        date_text = date_elem.get_text(strip=True) if date_elem else None
                        time_text = time_elem.get_text(strip=True) if time_elem else None

                        # Combine date and time for display
                        datetime_text = f"{date_text} {time_text}" if date_text and time_text else date_text

                        # Parse the date
                        event_date = self.parse_date(date_text) if date_text else None

                        # Check availability status
                        status_elem = perf_link.find('span', class_='tn-prod-list-item__perf-status')
                        action_elem = perf_link.find('span', class_='tn-prod-list-item__perf-action')

                        if status_elem and 'Sold Out' in status_elem.get_text():
                            status = 'sold_out'
                        elif action_elem and 'Buy tickets' in action_elem.get_text():
                            status = 'available'
                        else:
                            status = 'unknown'

                        events.append({
                            'id': event_id,
                            'title': title,
                            'url': perf_url,
                            'datetime_text': datetime_text,
                            'date': event_date,
                            'status': status
                        })
                    except Exception as e:
                        print(f"Error parsing performance: {e}")
                        continue

            except Exception as e:
                print(f"Error parsing event item: {e}")
                continue

        return events

    def should_monitor_event(self, event):
        """Check if an event matches our monitoring criteria"""
        event_id = event['id']
        title = event['title'].lower()

        for monitored in self.monitored_events:
            monitored_lower = monitored.lower()
            # Check if it matches by ID or title keyword
            if monitored_lower in event_id.lower() or monitored_lower in title:
                return True

        return False

    def send_pushover_notification(self, title, message, url, priority=0):
        """Send notification via Pushover"""
        if not self.pushover_user_key or not self.pushover_app_token:
            print("  ⚠️  Pushover not configured (missing user key or app token)")
            return False

        try:
            print(f"  📤 Sending Pushover notification...")
            print(f"     Title: {title}")
            print(f"     User Key: {self.pushover_user_key[:8]}...")
            print(f"     App Token: {self.pushover_app_token[:8]}...")

            response = requests.post(
                'https://api.pushover.net/1/messages.json',
                data={
                    'token': self.pushover_app_token,
                    'user': self.pushover_user_key,
                    'title': title,
                    'message': message,
                    'url': url,
                    'priority': priority,
                    'sound': 'pushover'
                },
                timeout=10
            )

            print(f"     Response status: {response.status_code}")
            print(f"     Response body: {response.text}")

            if response.status_code == 200:
                print("  ✅ Pushover notification sent successfully!")
                return True
            else:
                print(f"  ❌ Pushover notification failed: {response.text}")
                return False

        except Exception as e:
            print(f"  ❌ Error sending Pushover notification: {e}")
            import traceback
            traceback.print_exc()
            return False

    def send_email_notification(self, subject, body, url, event_title):
        """Send notification via Gmail"""
        if not self.gmail_user or not self.gmail_app_password or not self.notify_email:
            return False

        try:
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

            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as server:
                server.login(self.gmail_user, self.gmail_app_password)
                server.send_message(msg)

            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def notify(self, event, is_new=True):
        """Send notifications via both services"""
        if is_new:
            title = f"SCAD Tickets Available!"
            message = f"{event['title']} ({event['datetime_text']}) - Tickets just became available!"
        else:
            title = f"SCAD Tickets Still Available"
            message = f"{event['title']} ({event['datetime_text']}) - Tickets are available!"

        pushover_sent = self.send_pushover_notification(title, message, event['url'])
        email_sent = self.send_email_notification(title, message, event['url'], event['title'])

        if pushover_sent:
            print("  ✓ Pushover notification sent")
        if email_sent:
            print("  ✓ Email notification sent")

        return pushover_sent or email_sent

    def send_test_notification(self, stats):
        """Send a test notification with monitoring stats"""
        print("\n📤 Sending test notification...")
        print(f"   Pushover configured: {bool(self.pushover_user_key and self.pushover_app_token)}")

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

        pushover_sent = self.send_pushover_notification(title, message, url, priority=-1)

        if pushover_sent:
            print("  ✅ Test notification sent successfully")
        else:
            print("  ❌ Test notification failed")

        return pushover_sent

    def monitor(self):
        """Main monitoring loop"""
        print(f"\n{'=' * 70}")
        print(f"Check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 70}")

        # Reload config to pick up any changes
        print("📋 Reloading configuration...")
        self.config = self.load_config()
        self.monitored_events = self.config.get('monitored_events', [])
        self.notify_all_available = self.config.get('notify_all_available', False)
        self.send_test_notifications = self.config.get('send_test_notifications', False)

        # Reload credentials
        creds = self.config.get('credentials', {})
        self.pushover_user_key = creds.get('pushover_user_key') or os.getenv('PUSHOVER_USER_KEY')
        self.pushover_app_token = creds.get('pushover_app_token') or os.getenv('PUSHOVER_APP_TOKEN')

        print(f"⚙️  Config loaded:")
        print(f"   • Test notifications: {self.send_test_notifications}")
        print(f"   • Notify all available: {self.notify_all_available}")
        print(f"   • Pushover user key: {'✓' if self.pushover_user_key else '✗'}")
        print(f"   • Pushover app token: {'✓' if self.pushover_app_token else '✗'}")

        # Parse the festival page
        all_events = self.parse_festival_page()

        if not all_events:
            print("⚠️  No events found (check parsing or connectivity)")
            return

        print(f"Found {len(all_events)} total screenings")

        # Filter to monitored events
        monitored_found = [e for e in all_events if self.should_monitor_event(e)]
        print(f"Monitoring {len(monitored_found)} of your selected events")

        active_count = 0
        passed_count = 0
        available_count = 0
        sold_out_count = 0

        for event in monitored_found:
            event_id = event['id']

            # Check if event has passed
            if event['date'] and self.is_event_passed(event['date']):
                if event_id not in self.previous_states or not self.previous_states[event_id].get('marked_passed'):
                    print(f"\n  📅 {event['title'][:45]} ({event['datetime_text']})")
                    print(f"     Event passed - removing from monitoring")
                    self.previous_states[event_id] = {'status': 'passed', 'marked_passed': True}
                passed_count += 1
                continue

            active_count += 1
            previous_status = self.previous_states.get(event_id, {}).get('status')
            current_status = event['status']

            print(f"\n  🎬 {event['title'][:45]}")
            print(f"     {event['datetime_text']}")
            print(f"     Status: {current_status} (was: {previous_status})")

            # Track stats
            if current_status == 'available':
                available_count += 1
            elif current_status == 'sold_out':
                sold_out_count += 1

            # Detect status change or notify all available
            if current_status == 'available':
                is_newly_available = previous_status in ['sold_out', 'unknown', None]

                if is_newly_available:
                    print(f"     🎉 TICKETS BECAME AVAILABLE!")
                    self.notify(event, is_new=True)
                elif self.notify_all_available:
                    print(f"     📢 Notifying (still available)")
                    self.notify(event, is_new=False)

            # Update state
            self.previous_states[event_id] = {
                'status': current_status,
                'title': event['title'],
                'datetime': event['datetime_text'],
                'last_checked': datetime.now().isoformat(),
                'marked_passed': False
            }

        self.save_state()

        print(f"\n{'=' * 70}")
        print(
            f"Summary: {active_count} active | {available_count} available | {sold_out_count} sold out | {passed_count} passed")
        print(f"{'=' * 70}")

        # Send test notification if enabled
        if self.send_test_notifications:
            print("\n🧪 Test notifications enabled - sending test notification...")
            stats = {
                'monitored': active_count,
                'available': available_count,
                'sold_out': sold_out_count,
                'passed': passed_count
            }
            self.send_test_notification(stats)
        else:
            print("\n💡 Tip: Enable 'Send test notification' in settings to verify Pushover is working")

    def run(self):
        """Run the monitor continuously"""
        print("=" * 70)
        print("SCAD Film Festival Ticket Monitor")
        print("=" * 70)
        print(f"Monitoring {len(self.monitored_events)} event(s)")
        print(f"Festival page: {self.festival_url}")
        print(f"Proxy enabled: {bool(self.proxy_api_key)}")
        print(f"Pushover enabled: {bool(self.pushover_user_key and self.pushover_app_token)}")
        print(f"Email enabled: {bool(self.gmail_user and self.gmail_app_password)}")
        print(f"Notify all available: {self.notify_all_available}")
        print(f"Test notifications: {self.send_test_notifications}")
        print("=" * 70)

        while True:
            try:
                self.monitor()

                # Use configured interval with some randomness
                base_interval = self.check_interval_minutes
                wait_minutes = random.uniform(base_interval - 5, base_interval + 5)
                wait_seconds = wait_minutes * 60

                print(f"\n💤 Sleeping for {wait_minutes:.1f} minutes...")
                time.sleep(wait_seconds)

            except KeyboardInterrupt:
                print("\n\n🛑 Monitor stopped by user")
                break
            except Exception as e:
                print(f"\n❌ Error in monitor loop: {e}")
                print("Waiting 5 minutes before retry...")
                time.sleep(300)


if __name__ == "__main__":
    monitor = TicketMonitor()
    monitor.run()