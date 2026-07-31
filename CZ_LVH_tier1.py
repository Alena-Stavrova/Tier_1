from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException
import time
import re
import random
import os
import traceback
import sys

# Initialize driver with None (to be changed later)
driver = None
wait = None
website_main = "https://cz.levenhuk.com/"

# Create the optimized driver (loads fast, limits images)
def create_optimized_driver():
    # Use Options class to customize WebDriver
    options = Options()
    # Wait for DOM to be interactive (instead of all resources to downloaded)
    options.page_load_strategy = 'eager'
    
    # Block all images, background networking and extensions
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-extensions')
    
    driver = webdriver.Chrome(options=options)
    
    # Longer timeout for initial load
    driver.set_page_load_timeout(60)
    
    return driver

def take_screenshot(name):
    # Create screenshot folder, name screenshot images
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")

    filename = f"screenshots/{name}_{int(time.time())}.png"
    driver.save_screenshot(filename)
    print(f"(Screenshot saved as: {filename})")
    return filename

# Step counter class to count step number automatically
class StepCounter:
    def __init__(self):
        self.step = 1
    
    def print_step(self, message):
        print(f"\n--- Step {self.step}: {message} ---")
        self.step += 1

# Container for general order data and functions
class ParentContext:
    def __init__(self):
        self.user_email = None
        self.user_phone = None

        self.sku = {
            'selected': None,
            'price_class': None,
            'price_class_type': 'flexible',  
            'unavailable': []   # Track unavailable SKUs
        }

        self.selected_delivery = None 

        self.selected_payment = None

        self.currency = None
        self.displays_cents = True
        self.free_shipping_phrase = None

        # Results summary
        self.summary = {
            'delivery_option': None,
            'payment_option': None,
            'basket_price': None,
            'order_result': None,
            'expected_fee': None,
            'order_fee': None}
    
    def get_sku_list(self, price_class):
        # Returns the SKU list for a specific price class
        return self.sku_lists['price_classes'][price_class]
    
    def get_all_skus(self):
        # Get all SKUs from both price classes
        all_skus = self.sku_lists['price_classes'][0] + self.sku_lists['price_classes'][1]
        return all_skus
    
    def mark_sku_unavailable(self, sku):
        # Add a SKU to the unavailable list
        if sku not in self.sku['unavailable']:
            self.sku['unavailable'].append(sku)

    def get_default_delivery(self):
        for option in self.delivery_options:
            if option.get('is_default', False):
                return option
        # If no default marked, return first one
        return self.delivery_options[0] if self.delivery_options else None
    
    def get_delivery_option_by_name(self, local_name):
        for option in self.delivery_options:
            if option['local_name'] == local_name:
                return option
        return None

    def get_available_payment_options(self):
        if not self.sku.get('price_class') is None:
            price_class = self.sku['price_class']
        else:
            price_class = None
        
        delivery_name = self.selected_delivery['local_name'] if self.selected_delivery else None

        available = []
        for option in self.payment_options:
            compatible = option.get('compatible_with', {})
            
            # Check delivery compatibility (if delivery is set)
            delivery_ok = True
            if delivery_name and 'delivery' in compatible:
                delivery_ok = delivery_name in compatible['delivery']
            
            # Check price class compatibility (if price class is set)
            price_ok = True
            if price_class is not None and 'price_class' in compatible:
                price_ok = price_class in compatible['price_class']
            
            if delivery_ok and price_ok:
                available.append(option)
        
        return available

    def get_default_payment(self):
        available = self.get_available_payment_options()

        for option in available:
            if option.get('is_default', False):
                return option
            
        return available[0] if available else None

    def get_cash_payment(self):
        for option in self.payment_options:
            if option.get('is_cash', False):
                return option
        return None
        
    def update_summary(self, **kwargs):
        self.summary.update(kwargs)

    def format_fee_display(self, amount, display_text):
            if display_text and 'TBD' in str(display_text).upper():
                self.summary['order_fee'] = display_text
                self.summary['order_fee_amount'] = None
            elif self.free_shipping_phrase and display_text == self.free_shipping_phrase:
                self.summary['order_fee'] = f"0 {self.currency}"
                self.summary['order_fee_amount'] = 0
            else:
                self.summary['order_fee'] = f"{amount} {self.currency}" if amount is not None else display_text
                self.summary['order_fee_amount'] = amount

class OrderContextCZ(ParentContext):
    def __init__(self):
        super().__init__()
        
        self.sku_lists = {
            'price_classes': {
                0: [79086, 74322, 81932, 72097, 83820], # Under 3000 CZK (109 CZK shipping)
        
                1: [17803, 79104, 67698, 72106, 83839]  # 3000+ CZK
        }
    }
        
        self.delivery_options = [
            {
                'local_name': 'vyzvednutí',
                'en_name': 'shop pickup',
                'opt_id': 'ID_SHIPPING_METHOD_ID_8',
                'is_default': True
                },
            {            
                'local_name': 'ppl parcel box',
                'en_name': 'ppl parcel box',
                'opt_id': 'ID_SHIPPING_METHOD_ID_26'
                },      
            {
                'local_name': 'doručení kurýrem',
                'en_name': 'courier',
                'opt_id': 'ID_SHIPPING_METHOD_ID_5'
                },
            {
                'local_name': 'expresní doručení',
                'en_name': 'express courier',
                'opt_id': 'ID_SHIPPING_METHOD_ID_28'
                }
            ]
          
        self.payment_options = [
            {
                'local_name': 'dobírka',
                'en_name': 'cash on delivery',
                'opt_id': 'ID_PAY_SYSTEM_ID_10',
                'is_default': True,
                'is_cash': True,
                'compatible_with': {
                    'delivery':['vyzvednutí', 'ppl parcel box', 'doručení kurýrem'],
                    'price_class': [0, 1]
                }
            },
            {
                'local_name': 'online platba kartou',
                'en_name': 'credit card',
                'opt_id': "ID_PAY_SYSTEM_ID_52",
                'compatible_with': {
                    'delivery':['vyzvednutí', 'ppl parcel box', 'doručení kurýrem', 'expresní doručení'],
                    'price_class': [0, 1]
                }
            },
            {
                'local_name': 'paypal',
                'en_name': 'paypal',
                'opt_id': 'ID_PAY_SYSTEM_ID_6',
                'compatible_with': {
                    'delivery':['vyzvednutí', 'ppl parcel box', 'doručení kurýrem', 'expresní doručení'],
                    'price_class': [0, 1]
                }
            }
        ]

        self.displays_cents = False
        self.currency = 'Kč'
        self.free_shipping_phrase = 'Doprava zdarma'
        
        self.fees = {
            'shipping': {
                'shop pickup': {
                    'any': {
                        'amount': 0,
                        'display': 'Doprava zdarma'
                    }
                },
                'courier': {
                    'under_3000': {
                        'amount': 109,  # Numeric for calculation
                        'display': '109 Kč'
                    },
                    'over_3000': {
                        'amount': 0,
                        'display': 'Doprava zdarma'
                    }
                },
                'ppl parcel box': {
                    'under_3000': {
                        'amount': 109,  
                        'display': '109 Kč'
                    },
                    'over_3000': {
                        'amount': 0,
                        'display': 'Doprava zdarma'
                }
            }
        }
    }

    
    def get_expected_shipping_fee(self):
        if not self.selected_delivery:
            return None, None

        delivery_name = self.selected_delivery['en_name']
        price_class = self.sku['price_class']  

        # Express delivery - 3rd party API, nothing to verify against
        if delivery_name == 'express courier':
            return None, None

        # Shop pickup
        if delivery_name == 'shop pickup':
            fee_data = self.fees['shipping'][delivery_name]['any']
            return fee_data['display'], fee_data['amount']
        
        # Standard courier and PPL
        else:
            if price_class == 0:  
                tier = 'under_3000'
            else:  
                tier = 'over_3000'

            fee_data = self.fees['shipping'][delivery_name][tier]
            return fee_data['display'], fee_data['amount']

    def get_expected_payment_fee(self):
        # No payment fees
        return None, None

    def get_expected_total_fee(self):
        ship_display, ship_amount = self.get_expected_shipping_fee()

        if ship_display is None and ship_amount is None:
             return None, None  # Express/third-party — no reference
        
        pay_display, pay_amount = self.get_expected_payment_fee()
        
        ship_amount = ship_amount or 0
        pay_amount = pay_amount or 0
        total_amount = ship_amount + pay_amount
        
        if total_amount == 0:
            display = self.free_shipping_phrase
        else:
            display = f'{total_amount} {self.currency}'
            
        return display, total_amount

def determine_price_class(payment_option):
    price_class_list = payment_option['compatible_with']['price_class']
    price_class = random.choice(price_class_list)
    return price_class

def get_payments_for_delivery(order, delivery_en_name):
    delivery_option = next(d for d in order.delivery_options if d['en_name'] == delivery_en_name)
    return [p for p in order.payment_options if delivery_option['local_name'] in p['compatible_with'].get('delivery', [])]
    
# Choose random sku, return a string and int price class
def choose_sku(order):
    price_class = order.sku['price_class']
    sku_list = order.get_sku_list(price_class)
    available_skus = [
        str(sku) for sku in sku_list 
        if str(sku) not in order.sku['unavailable']
    ]
        
    if available_skus:
        selected_sku = random.choice(available_skus)
        order.sku['selected'] = selected_sku
            
        print(f"✓ Selected SKU: {selected_sku} (Price class: {price_class})")
        return selected_sku
    
    # If we get here, both classes have no available SKUs
    print("✗ WARNING: No available SKUs in either price class!")
    return None

def choose_address():
    # Define a list of shipping addresses
    shipping_addresses = [
    {
        'country': 'Česká republika',
        'city': 'Praha',
        'address': 'V Nových domcích 661/10',
        'postal_code': '102 00'
    },
    {
        'country': 'Česká republika',
        'city': 'Brno', 
        'address': 'Zborovská 937/1',
        'postal_code': '616 00'
    },
    {
        'country': 'Česká republika',
        'city': 'Pardubice',
        'address': 'Ve Stezkách 215',
        'postal_code': '530 03'
    }
]
    address = random.choice(shipping_addresses)
    return(address) #returns a dictionary

def extract_price(price_text):
    # Remove all characters except digits and the comma/dot
    # Only EU, US have dot (23.95 EU - no need to replace), the rest have comma
    clean_text = re.sub(r'[^\d,]', '', price_text)
    # Replace comma with dot 
    clean_text = clean_text.replace(',', '.')   
    try:
        return float(clean_text)
    except ValueError:
        return None
  
def close_cookie_popup(): 
    try:
        accept_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".cky-btn.cky-btn-accept"))
        )
        accept_button.click()
        print("Cookie popup closed")
        time.sleep(1)
        return True    
     
    except Exception as e:
        return False # Popup already closed or not present

def search_for_sku(sku):
    try:
        print("Navigating to main page...")
        driver.get(website_main)
        time.sleep(3)

        close_cookie_popup()
        
        print("Opening search box...")
        search_box = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "header__search")))
        search_box.click()
        time.sleep(1)
        
        print("Entering SKU...")
        search_input = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "search__input")))
        search_input.clear()
        search_input.send_keys(str(sku))
       
        print("Submitting search...")
        search_input.send_keys(Keys.ENTER)
        print("Waiting for results to load...")

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, ".b-48.pb-md-24"))
            )
        except:
            time.sleep(5)

        # Find card SKU line, like "Product ID: 83836"
        card_sku_elem = driver.find_element(By.CLASS_NAME, 'catalog-card__article')
        card_sku = card_sku_elem.text[-5:]
        print(f"SKU on the product card is: {card_sku}")
        
        # Scroll to the element to take screenshot
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_sku_elem)
        time.sleep(2)
        take_screenshot("search_results")

        if sku == card_sku:        
            print("Search completed successfully")
            return True
        else:
            print(f"✗ First found item doesn't match the search: looked for {sku}, first item is {card_sku}")
            return False
        
    except Exception as e:
        print(f"✗ Search failed: {str(e)}")
        take_screenshot("search_error")
        return False

def is_item_available(order):
    # Is only applied when sku != None
    sku = order.sku['selected']
    try:
        search_for_sku(sku)
        price_text = driver.find_element(By.CLASS_NAME, "catalog-card__price").text.lower()
        # Check language file for the translations: out of stock, discontinued, coming soon
        unavailable_indicators = ['vyprodáno', 'už není v nabídce', 'již brzy na skladě']
        if any(indicator in price_text for indicator in unavailable_indicators):
            return False, price_text
        else:
            cart_button = driver.find_element(By.CLASS_NAME, "catalog-card__cart")
            if cart_button.is_displayed():
                return True, "available"
            else:
                return False, "unclear"

    except Exception as e:
        return False, str(e)

def get_offer_id(sku):
    # Offer ID is in data-id
    try:
        print(f"Finding offer ID for SKU: {sku}")
        
        # Find the catalog-card container that contains SKU text and get its data-id
        offer_id_xpath = f"//div[contains(@class, 'catalog-card') and .//div[contains(@class, 'catalog-card__article') and contains(text(), '{sku}')]]"
        
        container = wait.until(EC.presence_of_element_located((By.XPATH, offer_id_xpath)))
        
        # Get the offer ID from data-id attribute
        offer_id = container.get_attribute('data-id')
        
        if offer_id:
            print(f"✓ Found offer ID: {offer_id}")
            return int(offer_id)
        else:
            print("✗ Failed to get offer ID: {str(e)}")
            take_screenshot("offer_id_error")
            return None
            
    except Exception as e:
        print(f"✗ Error finding offer ID: {str(e)}")
        return None

def add_to_cart_via_api(offer_id, quantity=1):
    # Simple API call - no UI updates attempted, relies on page refresh to update the cart
    try:
        print(f"Adding offer {offer_id} to cart via API...")
        
        script = f"""
            fetch('/rest/methods/user/basket/change', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{offerId: {offer_id}, quantity: "{quantity}"}})
            }})
            .then(response => response.json())
            .then(data => {{
                console.log('API Response:', data);
                // Store success state for verification
                window.lastCartAdd = {{
                    success: true,
                    offerId: {offer_id},
                    timestamp: Date.now()
                }};
            }})
            .catch(error => {{
                console.error('API Error:', error);
                window.lastCartAdd = {{success: false, error: error.message}};
            }});
        """
        
        driver.execute_script(script)
        time.sleep(2)  # Wait for API call
        
        # Verify it worked
        check_script = """
            return window.lastCartAdd || {success: false, error: 'No response'};
        """
        result = driver.execute_script(check_script)
        
        if result.get('success'):
            print(f"✓ API call successful for offer {offer_id}")
            return True
        else:
            print(f"✗ API call failed: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"✗ Error in API call: {e}")
        return False

def navigate_to_cart_directly():
    # Navigate to the cart page directly by URL
    try:
        cart_url = website_main + "basket/"
        print(f"Navigating to cart URL: {cart_url}")
        
        driver.get(cart_url)
        time.sleep(3)
        
        # Check if we're on a cart page
        current_url = driver.current_url.lower()
        if "basket" in current_url:
            print("✓ Successfully navigated to cart page")
            return True
        else:
            print(f"✗ Not on cart page. Current URL: {driver.current_url}")
            return False
        
    except Exception as e:
        print(f"✗ Failed to navigate to cart: {str(e)}")
        take_screenshot("cart_navigation_error")
        return False

def check_cart_contents(sku, expected_quantity=1):
    # Verify our item is in the basket
    cart_items = driver.find_elements(By.CSS_SELECTOR, 
        "div[class*='cart-table__item'][id^='basket-item-']")
    total_qty = 0
    found = False
    
    for cart_item in cart_items:  # cart_item is the whole DIV for a basket item
        if str(sku) in cart_item.text:
            found = True
            # Get quantity directly in element counter
            qty_input = cart_item.find_element(By.CSS_SELECTOR, 
                "[data-entity='basket-item-quantity-field']")
            qty = int(qty_input.get_attribute('value'))
            total_qty += qty
            print(f"✓ Found SKU {sku}, quantity: {qty}")
    
    if not found:
        print(f"✗ SKU {sku} not found")
        return False
    
    print(f"Total quantity: {total_qty}, Expected: {expected_quantity}")
    return total_qty == expected_quantity

def get_total_price_basket(order):
    # Extract the total price from the Cart price block
    try:
        price_text = driver.find_element(By.CLASS_NAME, 'cart-panel__price').text
        price = extract_price(price_text)
        if price is not None:
            order.summary['basket_price'] = price
            return price

        print("✗ Could not find total price on page")
        return None
        
    except Exception as e:
        print(f"✗ Error extracting price: {str(e)}")
        return None

def proceed_to_checkout():
    # Click the checkout button, verify Basket > Order page
    try:
        checkout_button = driver.find_element(By.CSS_SELECTOR, "[data-entity='basket-checkout-button']")
        if checkout_button and checkout_button.is_displayed():
            print(f"Found checkout button")
                                
        if not checkout_button:
            raise Exception("✗ Could not find checkout button")
        
        print("Clicking checkout button...")
        checkout_button.click()
        
        # Wait for the order page to load
        print("Waiting for order page to load...")
        WebDriverWait(driver, 5).until(
            EC.url_contains("order")
        )
        
        # Verify we're on the order page
        current_url = driver.current_url.lower()
        if "order" in current_url:
            print(f"✓ Successfully navigated to order page: {driver.current_url}")
            return True
        else:
            print(f"✗ Not on order page. Current URL: {driver.current_url}")
            take_screenshot("not_on_order_page")
            return False
        
    except Exception as e:
        print(f"✗ Failed to proceed to checkout: {str(e)}")
        take_screenshot("checkout_error")
        return False

def _wait_for_payment_options(order):
    # Helper function that verifies all the payment buttons are interactable after express button appeared
    
    # First, wait for the express delivery option to appear 
    # This is the last element to load via third-party API
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 
                "label[for='ID_SHIPPING_METHOD_ID_28']"))
        )
        print("Express delivery option loaded")
        time.sleep(1)  # Extra buffer for the page to finish rebuilding after express arrives
    except:
        print("No express delivery option found (or already loaded)")

    compatible_options = order.get_available_payment_options()
    
    if not compatible_options:
        print("✗ No compatible payment options to wait for")
        return True
    
    expected_ids = [opt['opt_id'] for opt in compatible_options]
    print(f"Waiting for {len(expected_ids)} payment options to be clickable...")

    for opt_id in expected_ids:
        try:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f"label[for='{opt_id}']"))
            )
        except:
            print(f"✗ Payment option {opt_id} did not become clickable")
            return False
        
    time.sleep(0.3)  # Small buffer after all are ready
    print("All payment options clickable")
    return True 

def get_checked_option_id(id_prefix):
    # Ground-truth read of which radio input is actually checked in the DOM right now
    # Returns the id string, or None if none are checked

    script = """
        var prefix = arguments[0];
        var inputs = document.querySelectorAll('input[id^="' + prefix + '"]');
        for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].checked) { return inputs[i].id; }
        }
        return null;
    """
    try:
        return driver.execute_script(script, id_prefix)
    except Exception:
        return None

def force_click_option(opt_id):
    # Clicking the label fires the site's own click handlers, force the underlying input's checked state + change event
    # Needed in case the label click alone gets swallowed by an in-progress re-render

    try:
        driver.execute_script(f"""
            var label = document.querySelector('label[for="{opt_id}"]');
            if (label) {{ label.click(); }}
        """)
    except Exception:
        pass
    try:
        driver.execute_script(f"""
            var input = document.getElementById('{opt_id}');
            if (input && !input.checked) {{
                input.checked = true;
                input.dispatchEvent(new Event('change', {{bubbles: true}}));
                input.dispatchEvent(new Event('click', {{bubbles: true}}));
            }}
        """)
    except Exception:
        pass

def wait_until_selection_stable(id_prefix, expected_id, stable_duration=1.0, timeout=12, poll_interval=0.15):
    # Poll the DOM until `expected_id` has been continuously checked for `stable_duration` seconds straight
    # Any time the checked option drifts away from expected_id, it re-clicks expected_id and restarts the stability clock.
    # Only moves on once things have genuinely settled, returns True if stable in time, False if it never settled (timeout).
    
    start = time.time()
    stable_since = None

    while time.time() - start < timeout:
        current = get_checked_option_id(id_prefix)

        if current == expected_id:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= stable_duration:
                return True
        else:
            if stable_since is not None:
                print(f"  ↳ Selection drifted from {expected_id} (now: {current}), re-clicking...")
            stable_since = None
            force_click_option(expected_id)

        time.sleep(poll_interval)

    final = get_checked_option_id(id_prefix)
    print(f"✗ '{expected_id}' never stabilized as checked (last seen: {final})")
    return False

def select_ppl(order):
# Separate function for PPL delivery, used in select_delivery_option()
    try:
        print("Selecting PPL delivery method...")
        ppl_option = order.get_delivery_option_by_name('ppl parcel box')
        if not ppl_option:
            print("✗ PPL parcel box option not found")
            return False
        
        ppl_element = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 
                f"label[for='{ppl_option['opt_id']}']"))
        )
        ppl_element.click()
        stable = wait_until_selection_stable("ID_SHIPPING_METHOD_ID_", ppl_option['opt_id'])
        if not stable:
            print("✗ Could not get PPL radio to stick")
            return False
        print("PPL delivery selected")

        # TODO - do we need this??
        if not _wait_for_payment_options(order):
            print("✗ Payment options not fully ready, but continuing...")
        
        print("Selecting PPL pickup point...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".result__item"))
        )
        pickup_buttons = driver.find_elements(By.CSS_SELECTOR, ".result__link")
        print(f"Found {len(pickup_buttons)} PPL pickup points")

        if not pickup_buttons:
            print("✗ No PPL pickup points found")
            return False
        
        # Choose a random pickup point
        chosen_button = random.choice(pickup_buttons)

        try:
            title_element = chosen_button.find_element(By.CSS_SELECTOR, ".result__item-title")
            point_name = title_element.text
            print(f"Selecting pickup point: {point_name}")
        except:
            print("Selecting random pickup point")

        # Scroll and click with JS fallback
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", 
            chosen_button
            )
        time.sleep(0.3)
        try:
            chosen_button.click()
        except:
            driver.execute_script("arguments[0].click();", chosen_button)

        print("Pickup point clicked, waiting for details to load...")
        time.sleep(2)

        print("Looking for selection button...")
        select_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Vybrat toto místo')]"))
        )
        select_button.click()
        print("Selection button clicked")
        time.sleep(2)

        print("✓ PPL pickup point selected successfully")
        return True
    
    except Exception as e:
        print(f"✗ Failed to select PPL pickup point: {str(e)}")
        take_screenshot("ppl_pickup_error")
        return False
    
def click_delivery_option(order):
    try:
        selected = order.selected_delivery

        selected_name = selected['local_name']
        selected_id = selected['opt_id']
        
        # Get default delivery from order context
        default = order.get_default_delivery()
        default_name = default['local_name'] if default else None

        # Only interact with UI if not default
        if selected_name != default_name:
            if selected_name == 'ppl parcel box':
                return select_ppl(order)
            else:
                try:
                    try:
                        # Find and click the delivery option label
                        delivery_label = wait.until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, 
                                f"label[for='{selected_id}']"))
                        )
                        print("Found delivery label, attempting to click...")
                
                        # Scroll to the label
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                            delivery_label
                        )
                        time.sleep(0.5)
                        delivery_label.click()

                    except:
                        # Fallback: click the radio input directly via JavaScript
                        print("Label not clickable, using JS click on radio input...")
                        try:
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, f"#{selected_id}"))
                            )
                            time.sleep(0.5)
                        except:
                            print(f"✗ Radio input #{selected_id} never appeared")
                            return False, selected_name
                    
                        driver.execute_script(
                            f"document.querySelector('#{selected_id}').click();"
                            )
                        # Also trigger change event in case the page listens for it
                        driver.execute_script(
                            f"document.querySelector('#{selected_id}').dispatchEvent(new Event('change', {{bubbles: true}}));"
                            )
                    time.sleep(1)
                    if not _wait_for_payment_options(order):
                        print("✗ Payment options not fully ready, but continuing...")

                    # Confirm the click actually stuck (page may re-render after express loads)
                    stable = wait_until_selection_stable("ID_SHIPPING_METHOD_ID_", selected_id)
                    if not stable:
                        print(f"✗ Could not get {selected_name} to stick")
                    
                    # Ground truth: read what's actually checked, don't just trust the intended click
                    actual_id = get_checked_option_id("ID_SHIPPING_METHOD_ID_")
                    actual_option = next(
                        (opt for opt in order.delivery_options if opt['opt_id'] == actual_id),
                        selected
                    )
                    actual_name = actual_option['local_name']
                    order.selected_delivery = actual_option # TODO - do we need this?
                
                    if actual_id == selected_id:
                        print(f"Confirmed delivery selection: {actual_name}")
                    else:
                        print(f"✗ Intended {selected_name} but DOM shows {actual_name} - reporting actual state")
                    return True
                
                except Exception as e:
                    print(f"✗ Failed to click delivery option {selected_name}: {str(e)}")
                    return False
        else:
            print(f"Using default delivery option ({default_name}), no action needed")
            return True
            
    except Exception as e:
        print(f"✗ Error in delivery selection process: {str(e)}")
        take_screenshot("delivery_option_error")
        return False

def click_payment_option(order):
    try:
        selected = order.selected_payment

        selected_name = selected['local_name']
        selected_id = selected['opt_id']

        # Get default payment from order context
        default = order.get_default_payment()
        default_name = default['local_name'] if default else None
        
        
        # Only interact with UI if real & not default
        if selected_name != default_name:
            try:
                payment_label = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                        f"label[for='{selected_id}']"))
                )
                print("Found payment label, attempting to click...")
                
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
                    payment_label
                )
                time.sleep(0.5)
                
                # CRITICAL: Re-find the element AFTER scrolling, before clicking
                payment_label = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                        f"label[for='{selected_id}']"))
                )
                payment_label.click()
                time.sleep(1)
                
            except (ElementClickInterceptedException, StaleElementReferenceException) as e:
                print(f"Click intercepted/stale ({type(e).__name__}), falling back to JS click...")
                force_click_option(selected_id)
            except Exception as e:
                print(f"Normal click failed ({str(e)}), attempting JS click fallback...")
                force_click_option(selected_id)

            # Confirm the click actually stuck; the express-delivery re-render can
            # silently snap the radio back to the default right after we click it
            stable = wait_until_selection_stable("ID_PAY_SYSTEM_ID_", selected_id)
            if not stable:
                print(f"✗ Could not get {selected_name} to stick")
                        
            # Ground truth: read what's actually checked in the DOM right now,
            # instead of trusting what we intended to click
            actual_id = get_checked_option_id("ID_PAY_SYSTEM_ID_")
            actual_option = next(
                (opt for opt in order.payment_options if opt['opt_id'] == actual_id),
                selected
            )
            actual_name = actual_option['local_name']
            order.selected_payment = actual_option # TODO - do we need this?

            if actual_id == selected_id:
                print(f"✓ Confirmed payment selection: {actual_name}")
            else:
                print(f"✗ Intended {selected_name} but DOM shows {actual_name} - reporting actual state")
             
            return True
            
        else:
            print(f"Using default payment option ({default_name}), no action needed")
            return True
            
    except Exception as e:
        print(f"✗ Error when clicking the payment option: {str(e)}")
        take_screenshot("payment_option_error")
        return False
                                                                                                    
def fill_order_form(user_email, test_phone):
    try:
        ship_to = choose_address() #is a dictionary
        country_name = ship_to['country']
        city_name = ship_to['city'] 
        print(f"Chosen address in: {country_name}, {city_name}")
        
        # Wait for the form to be present
        WebDriverWait(driver, 15).until(EC.presence_of_element_located(
            (By.ID, "EMAIL"))
        )
        print("Form found, starting to fill fields...")
        
        # Contact information
        print("Filling contact information...")
        
        # Email field
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.ID, "EMAIL"))
            )
            email_field.clear()
            email_field.send_keys(user_email)
            print("Email field filled")
        except Exception as e:
            print(f"✗ Error with email field: {str(e)}")
            take_screenshot("email_field_error")
            return False
        
        # Phone field
        try:
            # Different selector - no ID
            phone_field = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.NAME, "ORDER_PROP_88"))
            )
            phone_field.clear()
            phone_field.send_keys(test_phone)
            print("Phone field filled")
            
        except Exception as e:
            print(f"✗ Error with phone field: {str(e)}")
            take_screenshot("phone_field_error")
            return False
        
        # Name field
        try:
            name_field = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.ID, "FIO_SHIP"))
            )
            name_field.clear()
            name_field.send_keys("Alena Auto Test")
            print("Name field filled")

        except Exception as e:
            print(f"✗ Error with name field: {str(e)}")
            take_screenshot("name_field_error")
            return False  
               
        # Shipping address
        print("Filling shipping address...")

        # Select country in dropdown menu using Select object
        try:
            close_cookie_popup()
            print(f"Selecting country: {country_name}")

            # Find the actual select element (visible, interactable)
            country_select = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "COUNTRY_SHIPPING"))
            )
    
            # Create Select object
            select = Select(country_select)
    
            # Try to select by visible text
            select.select_by_visible_text(country_name)
            print(f"{country_name} is selected")
    
            time.sleep(1)
    
        except Exception as e:
            print(f"✗ Error with country field: {e}")
            traceback.print_exc()
            take_screenshot("country_field_error")
            return False
                    
        # City field 
        try:
            # Wait for the whole order form container to be fully rendered
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "bx-soa-order-form"))
            )
            time.sleep(1)  # Small buffer for JS layout calculations
    
            # Now wait for city field specifically, with retry
            city_field = None
            for attempt in range(3):
                try:
                    city_field = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.ID, "CITY_SHIP"))
                    )
            
                    # Scroll into view
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", 
                        city_field
                    )
                    time.sleep(0.3)
            
                    city_field.click()
                    break  # Success!
            
                except Exception as click_error:
                    print(f"Attempt {attempt + 1}/3 failed: {str(click_error)[:100]}")
                    time.sleep(2)
    
            if city_field is None:
                raise Exception("Failed to click city field after 3 attempts")
    
            city_field.clear()
            city_field.send_keys(city_name)
            print("City field filled")
    
            city_field.send_keys(Keys.TAB)
            time.sleep(0.5)
    
        except Exception as e:
            print(f"✗ Error with city field: {str(e)}")
            take_screenshot("city_field_error")
            return False
        
        # Address field
        try:
            # Wait for page to stabilize after city selection (cart may be reloading)
            try:
                WebDriverWait(driver, 15).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, "#CART-SIDEBAR-TARGET.loader"))
                )
                print("Loader disappeared")
                time.sleep(0.5)
            except:
                print("Loader not found or already gone")

            # Wait for delivery section to stabilize (express option may be loading)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "bx-delivery-method"))
            )
            time.sleep(0.5)
                
            address_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "ADDRESS_SHIP"))
            )
            
            # Use JS to focus and set value (bypasses overlay issues)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", address_field)
            time.sleep(0.3)
            driver.execute_script("arguments[0].focus();", address_field)
            driver.execute_script("arguments[0].value = '';", address_field)
            driver.execute_script("arguments[0].value = arguments[1];", address_field, ship_to['address'])
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", address_field)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", address_field)
            print("Address field filled")
                        
            # Press Tab to move to next field
            address_field.send_keys(Keys.TAB)
            time.sleep(0.5)
            
        except Exception as e:
            print(f"✗ Error with address field: {str(e)}")
            take_screenshot("address_field_error")
            return False
        
        # Postal code field
        try:
            postal_code_field = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "ZIP_SHIP"))
            )

            # Use JS to focus and set value (bypasses overlay issues)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", postal_code_field)
            time.sleep(0.3)
            driver.execute_script("arguments[0].focus();", postal_code_field)
            driver.execute_script("arguments[0].value = '';", postal_code_field)
            driver.execute_script("arguments[0].value = arguments[1];", postal_code_field, ship_to['postal_code'])
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", postal_code_field)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", postal_code_field)
            print("Postal code field filled")

            # Wait for delivery/payment section to fully re-render after address is complete
            # (Express delivery option and updated payment list may be loading via API)
            print("Waiting for delivery options to stabilize...")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "bx-delivery-method"))
            )
            # Wait for at least one payment label to be visible (section fully rebuilt)
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#bx-payment-method label"))
            )
            time.sleep(0.5)
            print("Delivery/payment section stabilized")
            
        except Exception as e:
            print(f"✗ Error with postal code field: {str(e)}")
            take_screenshot("postal_code_field_error")
            return False
        
        # Billing address is the same as shipping (default tick remains)
        print("Billing address remains same as shipping (default)")

        # Order comment (2 lines)
        try:
            comment_field = driver.find_element(By.ID, "ORDER_DESCRIPTION")
            driver.execute_script('arguments[0].value = "Alena Auto Test\\nThis order was made by Alena\'s helpful minions";', comment_field)
            print("Comment field filled")
        
        except Exception as e:
            print(f"✗ Error with comment field: {str(e)}")
            take_screenshot("comment_field_error")
        
        take_screenshot("order_form_filled")
        print("✓ Order form filled successfully")
        return True
        
    except Exception as e:
        print(f"✗ Error filling order form: {str(e)}")
        # Add traceback to see where it's failing
        traceback.print_exc()
        take_screenshot("order_form_error")
        return False

def verify_order_fee(order):
    try:
        print("Verifying order fees...")
        time.sleep(2)
        
        # Get actual fee from page
        fee_element = wait.until(
            EC.presence_of_element_located((By.ID, "bx-cost-shipping"))
        )    
        actual_fee = fee_element.text
        print(f"Actual fee on page: '{actual_fee}'")

        expected_display, expected_amount = order.get_expected_total_fee()
        # Only write it in the summary if not None
        if not (expected_display is None and expected_amount is None):
            order.summary['expected_fee'] = expected_display
        
        # Handle non-verifiable fees (express/third-party)
        if expected_display is None and expected_amount is None:
            # No reference – just capture and log
            if actual_fee == order.free_shipping_phrase:
                actual_amount = 0
            else:
                actual_amount = extract_price(actual_fee)  # None if not a number
            order.format_fee_display(actual_amount, actual_fee)
            print(f"Fee (non-verifiable): {actual_fee}")
            return True, actual_fee
        
        # Compare display strings
        if actual_fee == expected_display:
            print(f"✓ Fee verified: {actual_fee}")
            if actual_fee == order.free_shipping_phrase:
                actual_amount = 0
            else:
                actual_amount = extract_price(actual_fee)
            order.format_fee_display(actual_amount, actual_fee)
            return True, actual_fee
        
        else:
            print(f"✗ Fee mismatch: Expected '{expected_display}', got '{actual_fee}'")
            # Store actual fee even on mismatch
            if actual_fee == order.free_shipping_phrase:
                actual_amount = 0
            else:
                actual_amount = extract_price(actual_fee)
            order.format_fee_display(actual_amount, actual_fee)
            return False, actual_fee
                
    except Exception as e:
        print(f"✗ Error verifying order fees: {str(e)}")
        take_screenshot("fee_verification_error")
        return False, "Error"

def place_order():
    # Finalize the order by clicking the checkout button on the order form
    try:
        print("Placing final order...")
        
        take_screenshot("before_final_order")
        
        # Find and click the checkout button
        checkout_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "submit"))
        )
        print(f"Found checkout button")
        
        # Scroll to button
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkout_button)
        time.sleep(1)
        checkout_button.click()
        return True
        
    except Exception as e:
        print(f"✗ Error in final order submission: {str(e)}")
        take_screenshot("final_order_error")
        return False
    
def get_order_number():
    # Get the order number from the URL of the confirmation page
    # URL is like: https://levenhuk.com/order/?ORDER_ID=T-B2C-US-41574
    try:
        current_url = driver.current_url
        if "ORDER_ID=" in current_url:
            # Slicing different number of characters for test ("T-") and regular orders
            # Will need to edit if > 99,999 orders
            if "T-" in current_url:
                order_num = current_url[-14:]
            else:
                order_num = current_url[-12:]
            print(f"✓ Order confirmed! Order number: {order_num}")
            return order_num
                
        else:
            print(f"✗ Order number is not in current url: '{current_url}'")
            return False
        
    except Exception as e:
        print(f"✗ Error in final order submission: {str(e)}")
        take_screenshot("final_order_error")
        return False

def reverify_before_submit(order, attr_name, options_list, id_prefix):
    # Final ground-truth check right before submitting — a late re-render (e.g. during
    # fee verification) can silently reset a selection after we already confirmed it
    intended = getattr(order, attr_name)
    if intended is None:
        return

    current_id = get_checked_option_id(id_prefix)
    if current_id and current_id != intended['opt_id']:
        print(f"⚠ {attr_name} drifted before submission: was {intended['local_name']}, attempting to re-select it...")
        force_click_option(intended['opt_id'])
        wait_until_selection_stable(id_prefix, intended['opt_id'])

        current_id = get_checked_option_id(id_prefix)
        final_option = next((o for o in options_list if o['opt_id'] == current_id), intended)
        setattr(order, attr_name, final_option)

        if current_id == intended['opt_id']:
            print(f"✓ Re-selected {intended['local_name']} successfully")
        else:
            print(f"✗ Could not restore {intended['local_name']}; proceeding with {final_option['local_name']}")

def generate_test_plan(order):
    # 4 orders to cover 4 deliveries and 3 payments, test both price classes
    
    # Get all options, not just third-party
    all_deliveries = order.delivery_options
    all_payments = order.payment_options
    
    plan = []
    
    # Strategy: pair each delivery with a unique payment for 3 orders, then pick a random payment for the 4th order.
    # Shop pickup is always free → either price class works.
    # Express delivery calculates independently → either price class works.
    # Courier and pickup points have 3000 Kč threshold → test one above, one below.
    
    # Order 1: Shop pickup (always free) + payment 1, any price class
    # Order 2: Courier + payment 2, pick random price class and remove it from the list
    # Order 3: Pickup points + payment 3, the remaining price class from Option 2
    # Order 4: Express delivery + a random payment (out of 2 available), any price class
    
    # Shuffle payments for variety
    shuffled_payments = random.sample(all_payments, len(all_payments))
    
    # Shop pickup — always free, any price class
    shop_pickup = next(d for d in all_deliveries if d['en_name'] == 'shop pickup')
    plan.append({
        'delivery': shop_pickup,
        'payment': shuffled_payments[0],
        'price_class': random.choice([0, 1])
    })
    
    # Courier and pickup points — randomly assign price classes, but different
    price_classes = [0, 1]
    random.shuffle(price_classes)
    
    courier = next(d for d in all_deliveries if d['en_name'] == 'courier')
    plan.append({
        'delivery': courier,
        'payment': shuffled_payments[1],
        'price_class': price_classes[0]  # Random (0 or 1)
    })
    
    pickup_points = next(d for d in all_deliveries if d['en_name'] == 'ppl parcel box')
    plan.append({
        'delivery': pickup_points,
        'payment': shuffled_payments[2],
        'price_class': price_classes[1]  # The other one
    })

    # Express courier - 3rd party calculation, any price class
    express_courier = next(d for d in all_deliveries if d['en_name'] == 'express courier')
    express_payments = get_payments_for_delivery(order, 'express courier')
    plan.append({
        'delivery': express_courier,
        'payment': random.choice(express_payments),
        'price_class': random.choice([0, 1])
    })
    
    print(f'Generated test plan with {len(plan)} combo(s)')
    print(f'Courier price class: {price_classes[0]} ({"paid" if price_classes[0] == 0 else "free"})')
    print(f'Pickup points price class: {price_classes[1]} ({"paid" if price_classes[1] == 0 else "free"})')
    return plan

def execute_single_order(order):
    global driver, wait
    user_email = order.user_email
    test_phone = order.user_phone
    
    try:
        # Initialize step counter
        # Initialize step counter
        step_counter = StepCounter()
        print("---------------LOGS FOR NERDS---------------")
        
        print(f'Chosen delivery: {order.selected_delivery['local_name']}')
        print(f'Chosen payment: {order.selected_payment['local_name']}')

        print("\nLaunching browser...")
        driver = create_optimized_driver()
        driver.maximize_window()
        wait = WebDriverWait(driver, 20)

        while True:
            # Only choose the skus that are NOT in unavailable_items
            my_sku = choose_sku(order)
            total_skus = order.get_all_skus()
            if my_sku != None:
                print(f"Chosen SKU: {str(my_sku)}")

                step_counter.print_step("Searching for SKU")
                # Avaialability check already includes search_for_sku
                available, status = is_item_available(order)
    
                if available:
                    print(f"✓ SKU {my_sku} is available")
                    break
                # If item is NOT available:
                else:
                    if len(order.sku['unavailable']) < len(total_skus): 
                        print(f"✗ SKU {my_sku} not available: {status}")
                        order.sku['unavailable'].append(str(my_sku))
                        time.sleep(1)  # Small delay before retry

            # If choose_sku() returns None, meaning all items are unavailable
            else:
                print("✗ All items are UNAVAILABLE")
                print("Closing the browser")
                driver.quit()
                sys.exit()
                #return?

        order.sku['selected'] = my_sku
        
        step_counter.print_step("Getting offer ID")
        offer_id = get_offer_id(my_sku)

        if offer_id:
            step_counter.print_step("Adding to cart")
                
            if add_to_cart_via_api(offer_id, 1):
                print("Refreshing page to synchronize UI")
                driver.refresh()
                time.sleep(1)
                step_counter.print_step("Navigating to cart")

                if navigate_to_cart_directly():
                    step_counter.print_step("Checking cart contents")
                    if check_cart_contents(my_sku):
                        step_counter.print_step("Getting cart total price")
                        basket_price = int(get_total_price_basket(order))

                        if basket_price is not None:
                            print(f"Cart total price: {basket_price} {order.currency}")
                                
                            step_counter.print_step("Proceeding to checkout")
                            take_screenshot("basket_before_checkout")
                                
                            if proceed_to_checkout():
                                step_counter.print_step("Filling order form")                                
                                fill_form_success = fill_order_form(user_email, test_phone)
                                
                                if fill_form_success:
                                    step_counter.print_step("Clicking delivery option")
                                    delivery_success = click_delivery_option(order)
                                    if delivery_success:
                                        order.summary['delivery_option'] = order.selected_delivery['local_name']
                                    
                                    step_counter.print_step("Clicking payment option")
                                    payment_success = click_payment_option(order)
                                    if payment_success:
                                        order.summary['payment_option'] = order.selected_payment['local_name']

                                    time.sleep(2)
                                    step_counter.print_step("Verifying delivery and payment fees...")
                                    fee_success, fee_display = verify_order_fee(order)
                                    if fee_success:
                                        order.summary['order_fee'] = fee_display
                                            
                                    step_counter.print_step("Placing order")

                                    reverify_before_submit(order, 'selected_payment', order.payment_options, "ID_PAY_SYSTEM_ID_")
                                    reverify_before_submit(order, 'selected_delivery', order.delivery_options, "ID_SHIPPING_METHOD_ID_")

                                    order.summary['payment_option'] = order.selected_payment['local_name']
                                    order.summary['delivery_option'] = order.selected_delivery['local_name']

                                    order_result = place_order()

                                    if order_result:
                                        print("✓ Order successfully placed!")
                                        time.sleep(3)
                                        step_counter.print_step("Getting the order number")
                                        test_order_num = get_order_number()

                                    else:
                                        print("✗ Failed to place order")                                                                                 
                                else:
                                    print("✗ Failed to fill order form") 
                            else:
                                print("\n✗ Failed to proceed to checkout")
                        else:
                            print("\n✗ Could not extract price from cart page")
                    else:
                        print("\n✗ Item was added but not found in cart")
                else:
                    print("\n✗ Failed to navigate to cart")
            else:
                print("\n✗ Failed to add item to cart via API")
        else:
            print("\n✗ Could not find offer ID for the product")
        
        print("\nProcess completed. Browser will close in 10 seconds.")

        print("----------ORDER INFO----------")
        if order_result:
            print(f"Order number: {test_order_num}") # Will return False in case of error
        else:
            print("Order number: order wasn't placed")
        print(f"Chosen SKU: {order.sku['selected']}")
        print(f"Item price: {order.summary['basket_price']} {order.currency}")
        print(f"Delivery option: {order.summary['delivery_option']}")
        print(f"Payment option: {order.summary['payment_option']}")


        # Shipping fees match check
        if fee_success:
            if order.summary.get('expected_fee'):
                print(f"Order fee (shipping + payment): ✓ As expected, {order.summary['order_fee']}")
            else:
                print(f"Order fee (shipping + payment): {order.summary['order_fee']} (not verified against reference)")
        else:
            print(f"✗ Shipping fees don't match: expected {order.summary.get('expected_fee', 'N/A')}, got {order.summary['order_fee']}")
                
        print("----------END----------")
        time.sleep(10)
        
    except Exception as e:
        print(f"\n✗ Script failed with error: {str(e)}")
        take_screenshot("main_script_error")          
   
    finally:
        driver.quit()

def run_test_plan(order, emails, order_counter):
    plan = generate_test_plan(order)
    c = 1
    email_switches = 0
    local_counter = order_counter  # Continuation of brand-wide count
   
    for combo in plan:
        # Check if we need to switch email mid-script
        if local_counter > 0 and local_counter % 5 == 0:
            email_switches += 1
            if email_switches < len(emails):
                order.user_email = emails[email_switches]
                print(f"Switched to email: {order.user_email}")
            else:
                print("✗ Out of emails! Cannot place more orders.")
                break

        order.selected_delivery = combo['delivery']
        order.selected_payment = combo['payment']
        order.sku['price_class'] = combo['price_class']

        print(f'COMBO {c}: {order.selected_delivery['local_name']} + {order.selected_payment['local_name']} + Price class {order.sku['price_class']}')
        execute_single_order(order)
        c += 1
        local_counter += 1
    
    orders_made = c - 1  # Actual orders placed
    # Return how many emails were used (0-indexed)
    return orders_made, email_switches

def main_cz_lvh(email, phone, emails=None, order_counter=0):
    global driver, wait
    
    if emails is None:
        emails = [email]  # Backward compatibility
    
    order = OrderContextCZ()
    order.user_email = email
    order.user_phone = phone
    
    orders_made, email_index = run_test_plan(order, emails, order_counter)
    return orders_made, email_index

if __name__ == "__main__":
    main_cz_lvh()

