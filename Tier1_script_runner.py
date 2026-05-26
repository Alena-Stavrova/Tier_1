# Russian websites
import RU_4GL_tier1 as ru_4gl
# EU Levenhuks
import CZ_LVH_tier1 as cz_lvh
import random

script_modules = {
    'ru': {
        'RU_4GL': ru_4gl,
    }
    #'levenhuk': {
        #'CZ_LVH': cz_lvh,
    #}
}

# Max orders per brand (with buffer for IT's variability)
num_orders_per_brand = {
    'ru': 6         # RU 4GL-3
    #'levenhuk': 3     # CZ-3
}

# Collect all emails upfront (2 per brand since max is 8, and 8/5 > 1)
all_emails = {}
for brand, max_orders in num_orders_per_brand.items():
    emails_needed = (max_orders + 4) // 5  # Ceiling division
    brand_emails = []
    print(f"\n--- {brand.upper()} ---")
    for i in range(emails_needed):
        email = input(f"Enter email {i+1} for {brand}: ")
        brand_emails.append(email)
    all_emails[brand] = brand_emails

test_phone = "+79444444444"

# Run each brand separately
for brand, modules in script_modules.items():
    emails = all_emails[brand]
    order_counter = 0  # Count orders made so far in this brand
    email_index = 0
    
    for script_name, module in modules.items():
        # Pass ALL remaining emails to the script, plus the starting index
        current_email = emails[email_index]
        remaining_emails = emails[email_index:]  # The email pool from this point
        
        main_function = getattr(module, f"main_{script_name.lower()}")
        
        print(f"\n{'='*60}")
        print(f"Running {script_name} with email: {current_email}")
        print(f"Backup emails available: {len(remaining_emails)-1}")
        print(f"{'='*60}")
        
        orders_made, new_email_index = main_function(current_email, test_phone, remaining_emails, order_counter)
        order_counter += orders_made
        
        # Update email_index from what the script tells us
        email_index += new_email_index  # Add the relative index change
        
        print(f"Orders so far for {brand}: {order_counter}, Email index: {email_index}")
