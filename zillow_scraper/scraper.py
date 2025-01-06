from playwright.sync_api import sync_playwright
from models import RentalProperty
from datetime import datetime, timedelta
import re
from typing import List
import logging

class ZillowScraper:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=False,  # Show the browser
            slow_mo=50  # Add slight delay to see actions
        )
        self.page = self.browser.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _extract_number(self, text: str) -> float:
        if not text:
            return 0.0
        return float(re.sub(r'[^\d.]', '', text))

    def _parse_property_card(self, card) -> RentalProperty:
        try:
            # Extract price
            price_text = card.query_selector('[data-test="property-card-price"]')
            if not price_text:
                logging.error("Price element not found")
                return None
            price = self._extract_number(price_text.inner_text())

            # Extract address
            address_elem = card.query_selector('address[data-test="property-card-addr"]')
            if not address_elem:
                logging.error("Address element not found")
                return None
            address = address_elem.inner_text()

            # Extract beds, baths, and sqft from the details list
            details_list = card.query_selector('ul.StyledPropertyCardHomeDetailsList-c11n-8-107-0__sc-1j0som5-0')
            if not details_list:
                logging.error("Details list not found")
                return None
            
            details_text = details_list.inner_text()
            
            # Extract beds
            beds_match = re.search(r'(\d+\.?\d*)\s*(?:bd|bed)', details_text)
            beds = self._extract_number(beds_match.group(1)) if beds_match else 0

            # Extract baths
            baths_match = re.search(r'(\d+\.?\d*)\s*(?:ba|bath)', details_text)
            baths = self._extract_number(baths_match.group(1)) if baths_match else 0

            # Extract square footage
            sqft_match = re.search(r'(\d+,?\d*)\s*sqft', details_text)
            sqft = self._extract_number(sqft_match.group(1)) if sqft_match else None

            # Calculate price per square foot
            price_per_sqft = round(price / sqft, 2) if sqft else None

            # Extract listing date from the badge
            date_badge = card.query_selector('.StyledPropertyCardBadge-c11n-8-107-0__sc-tmjrig-0')
            listing_date = datetime.now()
            if date_badge:
                date_text = date_badge.inner_text()
                if 'days ago' in date_text:
                    days = int(re.search(r'(\d+)', date_text).group(1))
                    listing_date = datetime.now() - timedelta(days=days)
            link = card.query_selector('a').get_attribute('href')

            return RentalProperty(
                address=address,
                price_per_month=price,
                bedrooms=beds,
                bathrooms=baths,
                square_feet=sqft,
                price_per_sqft=price_per_sqft,
                listing_date=listing_date,
                link=link
            )
        except Exception as e:
            logging.error(f"Error parsing property card: {e}")
            return None

    def scrape_rentals(self, url: str) -> List[RentalProperty]:
        try:
            self.page.goto(url)
            self.page.wait_for_selector('[data-test="property-card"]', timeout=30000)
            
            properties = []
            processed_addresses = set()
            scroll_attempts = 0
            max_attempts = 20  # Maximum number of scroll attempts
            
            while scroll_attempts < max_attempts:
                # Get current height
                current_height = self.page.evaluate('window.pageYOffset')
                
                # Process visible cards
                property_cards = self.page.query_selector_all('[data-test="property-card"]')
                for card in property_cards:
                    property_data = self._parse_property_card(card)
                    if property_data and property_data.address not in processed_addresses:
                        properties.append(property_data)
                        processed_addresses.add(property_data.address)
                        print(f"Found property: {property_data.address}")
                
                # Scroll with multiple methods to ensure it works
                self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                self.page.wait_for_timeout(1000)  # Wait for content to load
                
                # Also try mouse wheel simulation
                self.page.mouse.wheel(0, 1000)
                self.page.wait_for_timeout(1000)
                
                # Check if we've moved from our previous position
                new_height = self.page.evaluate('window.pageYOffset')
                
                # If we haven't moved, try a different scroll method
                if new_height == current_height:
                    # Try JavaScript scroll
                    self.page.evaluate('''
                        window.scrollBy({
                            top: 1000,
                            behavior: 'smooth'
                        });
                    ''')
                    self.page.wait_for_timeout(1500)
                    
                    # Check again if we moved
                    final_height = self.page.evaluate('window.pageYOffset')
                    if final_height == current_height:
                        scroll_attempts += 1
                        if scroll_attempts >= max_attempts:
                            print("Reached maximum scroll attempts or bottom of page")
                            break
                    else:
                        scroll_attempts = 0  # Reset attempts if we successfully scrolled
                else:
                    scroll_attempts = 0  # Reset attempts if we successfully scrolled
                
                # Wait for any new content to load
                self.page.wait_for_timeout(1000)
            
            print(f"Total properties found: {len(properties)}")
            return properties

        except Exception as e:
            logging.error(f"Error scraping rentals: {e}")
            return []
