from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import random
import os
import traceback
import sys

# Initialize driver with None (to be changed later)
driver = None
wait = None
website_main = "https://4glaza.ru/"

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
        self.currency = None

        self.sku = {
            'selected': None,
            'price_class': None, # Just 1 price class here (price class 0)
            'price_class_type': 'flexible', 
            'unavailable': []   # Track unavailable SKUs
        }

        self.selected_delivery = None 

        self.selected_region = None

        self.selected_payment = None

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
        all_skus = self.sku_lists['price_classes'][0]
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
        if not self.selected_delivery:
            return self.payment_options.copy()
        
        delivery = self.selected_delivery
        compatible = delivery.get('compatible_with', {})
        allowed_payments = compatible.get('payment', [])
    
        # Also check region if set
        region = self.sku.get('region')
        allowed_regions = compatible.get('region', [])
    
        if region and allowed_regions and region not in allowed_regions:
            return []  # This delivery isn't available in this region
    
        available = [
            p for p in self.payment_options
            if p['en_name'] in allowed_payments
        ]
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

# Container for all order-related data
class OrderContextRU(ParentContext):
    def __init__(self):
        super().__init__()
        self.currency = '₽'
        self.display_cents = False
    
        self.sku_lists = {
            'price_classes': {
                0: [77830, 86570, 76825, 69037, 79583, 
                    78374, 72111, 81698, 80335, 85312]
            }
        }

        self.regions = ['Moscow', 'St. Petersburg', 'regions']

        self.delivery_options = [
            # Moscow default = Доставка курьером, no action
            # St. Pete default = Самовывоз из магазина + confirm shop
            # Regions default = Доставка курьером СДЭК, no action

            {            
                'local_name': 'самовывоз (Санкт-Петербург)',
                'en_name': 'shop pickup (St. Petersburg)',
                'opt_id': 'ID_SHIPPING_METHOD_ID_6',
                'is_default': True,
                'compatible_with': {
                    'region': ['St. Petersburg'],
                    'payment': ['credit card', 'bank transfer', 'yandex split']
                }
                # Академическая - только предоплаченные заказы!
                },
            {
                'local_name': 'доставка курьером (сдэк)',
                'en_name': 'courier (SDEK)',
                'opt_id': 'ID_SHIPPING_METHOD_ID_8',
                'is_third_party': True,
                'compatible_with': {
                    'region': ['St. Petersburg', 'regions'],
                    # "Оплата при получении" = "cash on delivery"
                    # "Наличными курьеру" = "cash on delivery (courier)"
                    'payment': ['credit card', 'cash on delivery (courier)', 'bank transfer', 'yandex split']
                }
            },
            {
                'local_name': 'доставка курьером (Москва)',
                'en_name': 'courier (Moscow)',
                'opt_id': 'ID_SHIPPING_METHOD_ID_2',
                'is_default': True,
                'compatible_with': {
                    'region': ['Moscow'],
                    'payment': ['credit card', 'cash on delivery (courier)', 'bank transfer', 'yandex split']
                }
            },
            {
                'local_name': 'срочная доставка курьером (Москва)',
                'en_name': 'express courier (Moscow)',
                'opt_id': 'ID_SHIPPING_METHOD_ID_3',
                'compatible_with': {
                    'region': ['Moscow'],
                    'payment': ['credit card', 'cash on delivery (courier)', 'bank transfer', 'yandex split']
                }
            },
            {
                'local_name': 'самовывоз (Москва)',
                'en_name': 'shop pickup (Moscow)',
                'opt_id': 'ID_SHIPPING_METHOD_ID_5',
                'compatible_with': {
                    'region': ['Moscow'],
                    'payment': ['credit card', 'bank transfer', 'yandex split']
                }
                # Лубянка - только предоплаченные заказы!
            },
            {
                'local_name': 'самовывоз (сдэк)',
                'en_name': 'pickup (SDEK)',
                'opt_id': 'ID_SHIPPING_METHOD_ID_9',
                'is_third_party': True,
                'compatible_with': {
                    'region': ['regions'],
                    # "Оплата при получении" = "cash on delivery"
                    # "Наличными курьеру" = "cash on delivery (courier)"
                    'payment': ['credit card', 'cash on delivery', 'bank transfer', 'yandex split']
                }
            },
            {
                'local_name': 'ems',
                'en_name': 'ems',
                'opt_id': 'ID_SHIPPING_METHOD_ID_4',
                'is_third_party': True,
                'compatible_with': {
                    'region': ['regions'],
                    # "Оплата при получении" = "cash on delivery"
                    # "Наличными курьеру" = "cash on delivery (courier)"
                    # "Наложенный платеж" = "cash on delivery (ems)"
                    'payment': ['credit card', 'bank transfer', 'cash on delivery (ems)', 'yandex split']
                }
            },
        ]

        self.payment_options = [
            {   # 5% discount for regions
                'local_name': 'оплата онлайн (банковская карта)',
                'en_name': 'credit card',
                'opt_id': 'ID_PAY_SYSTEM_ID_10',
                'is_default': True,
                'is_discount': True,
                'is_third_party': True,
            },
            {
                'local_name': 'банковский перевод',
                'en_name': 'bank transfer',
                'opt_id': 'ID_PAY_SYSTEM_ID_2',
            },
            {
                'local_name': 'яндекс сплит',
                'en_name': 'yandex split',
                'opt_id': 'ID_PAY_SYSTEM_ID_15',
            },
            {   'local_name': 'наличными курьеру',
                'en_name': 'cash on delivery (courier)',
                'opt_id': 'ID_PAY_SYSTEM_ID_8',
            },
            {   'local_name': 'оплата при получении',
                'en_name': 'cash on delivery',
                'opt_id': 'ID_PAY_SYSTEM_ID_5',
            },
             {   'local_name': 'наложенный платеж',
                'en_name': 'cash on delivery (ems)',
                'opt_id': 'ID_PAY_SYSTEM_ID_9',
            }
        ]

        self.fees = {
            'shipping': {                
                'shop pickup (St. Petersburg)': {
                        'display': 'Бесплатная доставка',
                        'amount': 0
                    },

                'shop pickup (Moscow)': {
                    'display': 'Бесплатная доставка',
                    'amount': 0
                    },

                'courier (Moscow)': {
                    'display': '350 ₽',
                    'amount': 350
                    },

                'express courier (Moscow)': {
                    'display': '500 ₽',
                    'amount': 500
                    } 
            }
        }

    def get_expected_shipping_fee(self):
        if not self.selected_delivery:
            return None, None
    
        # Third-party deliveries - no reference price, can't verify, skip
        if self.selected_delivery.get('is_third_party'):
            return None, None
    
        # Our own deliveries with predetermined costs
        delivery_name = self.selected_delivery['en_name']
        fee_data = self.fees['shipping'].get(delivery_name)
        return fee_data['display'], fee_data['amount'] if fee_data else (None, None)
    
    def get_expected_discount(self):
        if not self.selected_payment:
            return None, None
        
        is_discount = self.selected_payment('is_discount', False)
        region = self.selected_region

        if is_discount and region == 'regions':
            # 5% discount for regions when paid with credit card
            discount = 0.05
        else:
            discount = 0
        return discount

# Choose random sku, return a string and int price class
def choose_sku(order):
    price_class = 0
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

def choose_address(order):
    # Define a list of shipping addresses
    shipping_addresses = {
    'Moscow': [
        # Maybe include zip code to check later?
        '109125 Москва Саратовская 19 строение 5', # Google/Dadata zips don't match, used Dadata
        '109028 Москва Яузский бульвар 15',
        '101000 Москва Чистопрудный бульвар 10 строение 2'
    ],
    'St. Petersburg': [
        '194017 СПб пр. Энгельса 66',
        '197101 СПб Большая Пушкарская 46 лит. А', # Google/Dadata zips don't match, used Dadata
        '191180 СПб наб. Реки Фонтанки 92'
    ],
    'regions': [
        '236004 Калининград, Аллея Смелых 25',
        '614051 Пермь Пономарева 56',
        '185031 Петрозаводск Кондопожская 8',
        '450080 Уфа Менделеева 191А',
        '364024 Грозный Лорсанова 28'# Google/Dadata zips don't match, used Dadata
    ] 
    }
    chosen_region = order.selected_region
    region_lib = shipping_addresses[chosen_region]

    address = random.choice(region_lib)
    return(address) #returns a string

def extract_price(price_text):
    # Remove all characters except digits and the comma/dot
    # Only EU, US have dot (23.95 EU - no need to replace), the rest have comma
    clean_text = re.sub(r'[^\d]', '', price_text)  
    try:
        return float(clean_text)
    except ValueError:
        return None
  
def close_cookie_popup(): 
    try:
        accept_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                "#cookie_notice_toast .btn.btn-outline-dark.btn-sm.ml-32.mr-32.flex-shrink-0"))
        )
        accept_button.click()
        print("Cookie popup closed")
        time.sleep(1)
        return True    
     
    except Exception as e:
        return False # Popup already closed or not present

def close_region_popup():
    try:
        decline_button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.ID, "cancelLocation"))
        )
        decline_button.click()
        print("Region popup closed")
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
        close_region_popup()
        
        print("Opening search box...")
        search_box = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "search__input")))
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
                EC.presence_of_element_located((By.CSS_SELECTOR, ".product-card.product-control.product-control_inited.product-card_inited"))
            )
        except:
            time.sleep(5)

        # Find card SKU line, like "Product ID: 83836"
        card_sku_elem = driver.find_element(By.CSS_SELECTOR, '.product-card__id.swiper-no-swiping')
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
        price_text = driver.find_element(By.CLASS_NAME, "product-card__price").text.lower()
        # Check language file for the translations: out of stock, discontinued, coming soon
        unavailable_indicators = ['нет в наличии', 'снят с производства', 'скоро в продаже']
        if any(indicator in price_text for indicator in unavailable_indicators):
            return False, price_text
        else:
            cart_button = driver.find_element(By.CSS_SELECTOR, ".btn.btn-primary.fi-before-cart")
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
        
        product_card = wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'product-card__name')))

        # Get the offer ID from data-id attribute
        url = product_card.get_attribute('href')
        print(url)
        offer_id = url[-5:]

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
    cart_items = driver.find_elements(By.CLASS_NAME, "cart-row__meta")
    total_qty = 0
    found = False
    
    for cart_item in cart_items:  # cart_item is the whole DIV for a basket item
        if str(sku) in cart_item.text:
            found = True
            # Get quantity directly in element counter
            qty_input = cart_item.find_element(By.XPATH, 
                "./ancestor::div[contains(@class, 'cart-item')]//input[@data-entity='basket-item-quantity-field']")
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
        price_text = driver.find_element(By.ID, 'total_price').text
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
    
def _select_pickup_location(order):
    try:
        # Wait for the pickup points container to appear
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "pickup-points"))
        )
        time.sleep(0.5)
        
        # Get all pickup point items (tile-radio divs)
        all_items = driver.find_elements(By.CSS_SELECTOR, ".pickup-points .tile-radio")
        print(f"Total pickup points found: {len(all_items)}")
        
        if not all_items:
            print("✗ No pickup locations found")
            return False
        
        # Filter out pre-pay-only locations (text-danger inside the label)
        usable_items = []
        for item in all_items:
            danger_warnings = item.find_elements(By.CLASS_NAME, "text-danger")
            if not danger_warnings:
                usable_items.append(item)
        
        if not usable_items:
            print("✗ All locations are pre-pay only!")
            take_screenshot("all_prepay_only")
            return False
        
        print(f"Found {len(usable_items)} usable locations (filtered out {len(all_items) - len(usable_items)} pre-pay only)")
        
        # Pick a random location
        chosen = random.choice(usable_items)
        
        # Get the location name from the label
        try:
            label = chosen.find_element(By.CSS_SELECTOR, ".form-check-label")
            location_name = label.text.split("\n")[0][:80]
            print(f"Selected: {location_name}")
        except:
            print("Could not extract location name")
        
        # Find the radio input and click its label
        radio_input = chosen.find_element(By.CSS_SELECTOR, "input[type='radio']")
        radio_id = radio_input.get_attribute("id")
        print(f"Radio ID: {radio_id}")
        
        # Click the label (more reliable than clicking the radio directly)
        label = chosen.find_element(By.CSS_SELECTOR, f"label[for='{radio_id}']")
        
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", 
            label
        )
        time.sleep(0.3)
        
        # Click the label via JS
        driver.execute_script("arguments[0].click();", label)
        time.sleep(1)
        
        # Verify the radio is checked
        is_checked = radio_input.is_selected()
        if is_checked:
            print("✓ Pickup location selected and confirmed")
        else:
            print("✗ Pickup click performed but radio not confirmed as checked")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to select pickup location: {str(e)}")
        traceback.print_exc()
        take_screenshot("pickup_selection_error")
        return False
    
    
def click_delivery_option(order):
    try:
        delivery = order.selected_delivery
        delivery_name = delivery['local_name']
        delivery_en = delivery['en_name']
        delivery_id = delivery['opt_id']

         # Step 1: Click the delivery radio/label 
        try:
            delivery_label = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, f"label[for='{delivery_id}']"))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", delivery_label
            )
            time.sleep(0.3)
            delivery_label.click()
            time.sleep(0.5)
            print(f"Selected delivery: {delivery_name}")
        except Exception as e:
            print(f"✗ Failed to click delivery: {str(e)}")
            return False
        
        # Step 2: Handle sub-actions based on delivery type
        if 'shop pickup' in delivery_en or 'pickup (SDEK)' in delivery_en:
            return _select_pickup_location(order)
        
        # Courier, express courier, EMS — no sub-action needed
        return True

    except Exception as e:
        print(f"✗ Error in delivery selection: {str(e)}")
        take_screenshot("delivery_option_error")
        return False


def click_payment_option(order):
    try:
        selected = order.selected_payment
        selected_name = selected['local_name']
        selected_id = selected['opt_id']

        # Only interact if not default
        default = order.get_default_payment()
        default_name = default['local_name'] if default else None
        
        if selected_name != default_name:
            try:
                # Find the payment option label
                payment_label = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                        f"label[for='{selected_id}']"))
                )
                print("Found payment label, attempting to click...")
                
                # Scroll to the label
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", 
                    payment_label
                )
                time.sleep(0.3)

                # Re-find after scroll to avoid stale element
                payment_label = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 
                        f"label[for='{selected_id}']"))
                )
                payment_label.click()
                time.sleep(1)
                
                print(f"✓ Option clicked: {selected_name}")
                return True
                
            except Exception as e:
                # Fallback: JavaScript click
                try:
                    print("Attempting JavaScript click fallback...")
                    driver.execute_script(
                        f"document.querySelector('label[for=\"{selected_id}\"]').click();"
                    )
                    time.sleep(1)
                    print(f"✓ Successfully selected {selected_name} via JavaScript")
                    return True
                except:
                    print(f"✗ Failed to click payment option {selected_name}: {str(e)}")
                    traceback.print_exc()
                    return False
        else:
            print(f"Using default payment option ({default_name}), no action needed")
            return True
            
    except Exception as e:
        print(f"✗ Error when clicking the payment option: {str(e)}")
        take_screenshot("payment_option_error")
        return False

                                                                                                  
def fill_order_form(user_email, test_phone, order):
    try:
        ship_to = choose_address(order) #is a dictionary
        print(f"Chosen address: {ship_to}")
        
        # Wait for the form to be present
        WebDriverWait(driver, 5).until(EC.presence_of_element_located(
            (By.ID, "bx-soa-order-form"))
        )
        print("Form found, starting to fill fields...")
        
        # Contact information
        print("Filling contact information...")
        
        # Email field
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.ID, "bx-input-order-EMAIL"))
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
                EC.visibility_of_element_located((By.NAME, "ORDER_PROP_66"))
            )
            phone_field.click()
            phone_field.clear()
            phone_field.send_keys(test_phone)
            print("Phone number entered")
    
            # Click "Отправить смс" button
            sms_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-sms-submit='send']"))
            )
            sms_button.click()
            time.sleep(0.5)
            print("SMS button clicked, phone field filled")
            
        except Exception as e:
            print(f"✗ Error with phone field: {str(e)}")
            take_screenshot("phone_field_error")
            return False
        
        # Name field
        try:
            name_field = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.ID, "bx-input-order-FIO_SHIP"))
            )
            name_field.clear()
            name_field.send_keys("Алена Авто Тест")
            print("Name field filled")

        except Exception as e:
            print(f"✗ Error with name field: {str(e)}")
            take_screenshot("name_field_error")
            return False  
        
         # Order comment (2 lines)
        try:
            comment_field = driver.find_element(By.ID, "bx-input-order-USER_DESCRIPTION")
            driver.execute_script('arguments[0].value = "Алена Авто Тест\\nЭтот заказ сделан моими усердными миньонами";', comment_field)
            print("Comment field filled")
        
        except Exception as e:
            print(f"✗ Error with comment field: {str(e)}")
            take_screenshot("comment_field_error")

        # Shipping address
        print("Filling shipping address...")

        # Check if address section exists at all
        try:
            # Scroll to the address section
            address_section = driver.find_element(By.CSS_SELECTOR, ".ts-wrapper")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", address_section)
            time.sleep(0.5)
    
            # Click the .ts-control to activate TomSelect
            ts_control = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".ts-control"))
            )
            ts_control.click()
            time.sleep(0.3)
    
            # Clear first via JavaScript (works on the div)
            driver.execute_script("""
                var input = document.querySelector('.ts-control input');
                if (input) {
                    input.value = '';
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                }
            """)
            time.sleep(0.3)
    
            # Now use Selenium to type character by character into the input
            # Find the input AFTER it's been activated by click
            address_input = driver.find_element(By.CSS_SELECTOR, ".ts-control input")
    
            # Type the full address string - send_keys on the input should work now
            # since we clicked .ts-control first to activate it
            address_input.send_keys(ship_to)
    
            print(f"Address typed: {ship_to}")
            print("Waiting for Dadata suggestions...")
            time.sleep(2)
    
            # Get the expected zip code
            expected_zip = ship_to[:6].strip()
            print(f"Expected zip: '{expected_zip}'")
    
            # Wait for suggestions dropdown
            suggestions = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".ts-dropdown .option, .option[data-selectable]"))
            )
    
            if not suggestions:
                time.sleep(1)
                suggestions = driver.find_elements(By.CSS_SELECTOR, ".ts-dropdown .option, .option[data-selectable]")
    
            print(f"Found {len(suggestions)} Dadata suggestions")
    
            # Find best match by zip code
            chosen = None
            for i, suggestion in enumerate(suggestions):
                text = suggestion.text.strip()
                print(f"  Option {i+1}: {text[:100]}")
        
                if expected_zip and text[:6] == expected_zip:
                    chosen = suggestion
                    print(f"  → Zip match!")
                    break
    
            if not chosen and suggestions:
                chosen = suggestions[0]
                print(f"  → No zip match, using first option")
    
            if chosen:
                chosen.click()
                time.sleep(1)
                print("Address selected")
            else:
                print("✗ No suggestions found")
                take_screenshot("no_address_suggestions")
                return False
        
        except Exception as e:
            print(f"✗ Error with address field: {str(e)}")
            traceback.print_exc()
            take_screenshot("address_field_error")
            return False
        
        # Billing address is the same as shipping (default tick remains)
        print("Billing address remains same as shipping (default)")
        
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
        # Skip verification for third-party deliveries (no reference price)
        if order.selected_delivery.get('is_third_party'):
            print("Third-party delivery - skipping fee verification (no reference price)")
            # Still capture the actual fee for the order summary
            try:
                fee_element = wait.until(
                    EC.presence_of_element_located((By.ID, "bx-cost-shipping"))
                )
                order.summary['order_fee'] = fee_element.text
            except:
                order.summary['order_fee'] = "unknown"
            return True, order.summary.get('order_fee')
        
        # For our own deliveries, verify against expected fees
        print("Verifying order fees...")
        time.sleep(2)

        fee_element = wait.until(
            EC.presence_of_element_located((By.ID, "bx-cost-shipping"))
        )    
        actual_fee_text = fee_element.text
        print(f"Actual fee on page: '{actual_fee_text}'")

        expected_display, expected_amount = order.get_expected_shipping_fee()
        order.summary['expected_fee'] = expected_display

        if actual_fee_text == 'Бесплатная доставка':
            actual_fee = 0
        else:
            actual_fee = extract_price(actual_fee_text)
        
        if actual_fee == expected_amount:
            print(f"✓ Fee verified: {actual_fee} {order.currency}")
            return True, actual_fee
        else:
            print(f"✗ Fee mismatch: Expected '{expected_display}, got '{actual_fee}'")
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
                order_num = current_url[-12:]
            else:
                order_num = current_url[-10:]
            print(f"✓ Order confirmed! Order number: {order_num}")
            return order_num
                
        else:
            print(f"✗ Order number is not in current url")
            return False
        
    except Exception as e:
        print(f"✗ Error in final order submission: {str(e)}")
        take_screenshot("final_order_error")
        return False
    
def generate_test_plan(order):
    all_deliveries = order.delivery_options
    all_payments = order.payment_options
    
    plan = []
    used_deliveries = set()
    used_payments = set()
    
    # 1. Handle the constrained pair first: EMS + наложенный платеж
    ems = next(d for d in all_deliveries if d['en_name'] == 'ems')
    ems_cod = next(p for p in all_payments if p['en_name'] == 'cash on delivery (ems)')
    
    plan.append({'region': 'regions', 'delivery': ems, 'payment': ems_cod})
    used_deliveries.add('ems')
    used_payments.add('cash on delivery (ems)')
    
    # 2. "Наличными курьеру" — only couriers. Pick a random courier.
    cod_courier = next(p for p in all_payments if p['en_name'] == 'cash on delivery (courier)')
    couriers = [d for d in all_deliveries if 'courier' in d['en_name']]
    chosen_courier = random.choice(couriers)
    chosen_region = random.choice(chosen_courier['compatible_with']['region']) 
    plan.append({'region': chosen_region, 'delivery': chosen_courier, 'payment': cod_courier})
    used_payments.add('cash on delivery (courier)')
    
    # 3. "Оплата при получении" — only pickups. Pick a random pickup.
    cod_pickup = next(p for p in all_payments if p['en_name'] == 'cash on delivery')
    pickups = [d for d in all_deliveries if 'pickup' in d['en_name'] or 'shop pickup' in d['en_name']]
    chosen_pickup = random.choice(pickups)
    chosen_region = random.choice(chosen_pickup['compatible_with']['region']) 
    plan.append({'region': chosen_region, 'delivery': chosen_pickup, 'payment': cod_pickup})
    used_payments.add('cash on delivery')
    
    # 4. Remaining 3 universally-compatible payments + remaining 4 deliveries
    remaining_payments = [p for p in all_payments if p['en_name'] not in used_payments]
    used_deliveries = {ems['en_name'], chosen_courier['en_name'], chosen_pickup['en_name']}
    remaining_deliveries = [d for d in all_deliveries if d['en_name'] not in used_deliveries]
    
    # Shuffle for variety
    random.shuffle(remaining_payments)
    
    # Pair each remaining delivery with a unique payment
    for i, delivery in enumerate(remaining_deliveries):
        if i < len(remaining_payments):
            chosen_region = random.choice(delivery['compatible_with']['region'])
            plan.append({'region': chosen_region,'delivery': delivery, 'payment': remaining_payments[i]})
            used_deliveries.add(delivery['en_name'])
    
    remaining_deliveries = [d for d in all_deliveries if d['en_name'] not in used_deliveries]
    # Any leftover deliveries? Pair with already-used payments
    if len(remaining_deliveries) > 0:
        for delivery in remaining_deliveries: 
            compatible_payment_name = random.choice(delivery['compatible_with']['payment'])
            compatible_payment = next(p for p in all_payments if p['en_name'] == compatible_payment_name)
            plan.append({'region': chosen_region,'delivery': delivery, 'payment': compatible_payment})
            used_deliveries.add(delivery['en_name'])
    
    print(f'Generated test plan with {len(plan)} combos')
    for i, combo in enumerate(plan):
        print(f"  {i+1}. {combo['delivery']['en_name']} + {combo['payment']['en_name']} + {combo['region']}")
    print(plan)
    return plan


# Main execution
def execute_single_order(order):
    global driver, wait
    user_email = order.user_email
    test_phone = order.user_phone
    
    try:
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
                                fill_form_success = fill_order_form(user_email, test_phone, order)
                                
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
        print(f'Chosen region: {order.selected_region}')
        print(f"Delivery option: {order.summary['delivery_option']}")
        print(f"Payment option: {order.summary['payment_option']}")


        if fee_success:
            if order.selected_delivery.get('is_third_party') or order.selected_payment.get('is_third_party'):
                print(f"Order fee (shipping + payment): {order.summary['order_fee']} (third-party, no reference to verify against)")
            else:
                print(f"Order fee (shipping + payment): ✓ As expected, {order.summary['order_fee']}")
        else:
            print(f"✗ Shipping fees don't match: expected {order.summary['expected_fee']}, got {order.summary['order_fee']}")
        
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
        order.selected_region = combo['region']

        print(f'COMBO {c}: {order.selected_delivery['local_name']} + {order.selected_payment['local_name']}')
        execute_single_order(order)
        c += 1
        local_counter += 1
    
    orders_made = c - 1  # Actual orders placed
    # Return how many emails were used (0-indexed)
    return orders_made, email_switches

def main_ru_4gl(email, phone, emails=None, order_counter=0):
    global driver, wait
    
    if emails is None:
        emails = [email]  # Backward compatibility
    
    order = OrderContextRU()
    order.user_email = email
    order.user_phone = phone
    
    orders_made, email_index = run_test_plan(order, emails, order_counter)
    return orders_made, email_index

if __name__ == "__main__":
    main_ru_4gl()

