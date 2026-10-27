"""Static configuration of the simulated organisation: purposes, preferences, vendors,
channels, properties. Shared by every organisation the simulator serves."""
from __future__ import annotations

CATALOGUE_CREATED_AT = "2025-03-04T09:12:44.512Z"
CONFIG_TREE = {"id": "iKgQKKDC", "created_at": "2025-03-04T09:12:44.512Z", "updated_at": "2026-06-18T14:45:10.207Z"}

# IAB TCF v2.2 purposes, Didomi string ids. `li` = legitimate interest is a valid legal basis.
# `appeal` scales the country opt-in rate when a user picks purposes one by one.
TCF_PURPOSES = [
    {"id": "cookies", "iab": 1, "li": False, "appeal": 1.25,
     "name": "Store and/or access information on a device"},
    {"id": "select_basic_ads", "iab": 2, "li": True, "appeal": 1.05, "name": "Use limited data to select advertising"},
    {"id": "create_ads_profile", "iab": 3, "li": False, "appeal": 0.7, "name": "Create profiles for personalised advertising"},
    {"id": "select_personalized_ads", "iab": 4, "li": False, "appeal": 0.7,
     "name": "Use profiles to select personalised advertising"},
    {"id": "create_content_profile", "iab": 5, "li": False, "appeal": 0.75,
     "name": "Create profiles to personalise content"},
    {"id": "select_personalized_content", "iab": 6, "li": False, "appeal": 0.8,
     "name": "Use profiles to select personalised content"},
    {"id": "measure_ad_performance", "iab": 7, "li": True, "appeal": 1.0, "name": "Measure advertising performance"},
    {"id": "measure_content_performance", "iab": 8, "li": True, "appeal": 1.1, "name": "Measure content performance"},
    {"id": "market_research", "iab": 9, "li": True, "appeal": 0.9,
     "name": "Understand audiences through statistics or combinations of data from different sources"},
    {"id": "improve_products", "iab": 10, "li": True, "appeal": 0.95, "name": "Develop and improve services"},
]

# Custom (Preference Management Platform) purposes with preferences and their value ids.
CUSTOM_PURPOSES = [
    {"id": "newsletter", "appeal": 0.6, "name": "Newsletter and editorial emails",
     "preferences": {
         "topics": {"name": "Topics", "multi": True,
                    "values": {"fashion": "Fashion", "home": "Home & living", "tech": "Tech", "sports": "Sports"}},
         "frequency": {"name": "Frequency", "multi": False,
                       "values": {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}},
     }},
    {"id": "personalized_offers", "appeal": 0.5, "name": "Personalised offers and promotions",
     "preferences": {
         "product_categories": {"name": "Product categories", "multi": True,
                                "values": {"women": "Women", "men": "Men", "kids": "Kids", "beauty": "Beauty"}},
     }},
    {"id": "partner_sharing", "appeal": 0.3, "name": "Share my data with selected partners", "preferences": {}},
]

PURPOSES = {p["id"]: p for p in TCF_PURPOSES + CUSTOM_PURPOSES}
LI_PURPOSES = [p["id"] for p in TCF_PURPOSES if p["li"]]
CHANNELS = {"email": "Email", "sms": "SMS", "push": "Push notifications"}

# (id, name, category, iab_id, uses_li, country). Ids follow Didomi's conventions: short ids for
# well-known partners, "<slug>-<8 chars>" for the rest, "c:<slug>" for organisation-created ones.
_VENDORS = [
    ("google", "Google Advertising Products", "advertising", 755, True, "US"),
    ("criteo", "Criteo SA", "advertising", 91, True, "FR"),
    ("facebook", "Meta Platforms Ireland", "advertising", None, False, "IE"),
    ("amazon", "Amazon Advertising", "advertising", 793, True, "US"),
    ("twitter", "X Corp", "social", None, False, "US"),
    ("linkedin", "LinkedIn Ireland", "social", 804, False, "IE"),
    ("tiktok-KZAUQLZ9", "TikTok Technology", "social", 1265, False, "IE"),
    ("pinterest-Xdb9kQ3M", "Pinterest Europe", "social", None, False, "IE"),
    ("snapchat-Hc8fYKqw", "Snap Inc.", "social", None, False, "US"),
    ("microsoft", "Microsoft Advertising", "advertising", 1126, True, "US"),
    ("appnexus", "Xandr (AppNexus)", "advertising", 32, True, "US"),
    ("rubicon-Gb6YpkCx", "Magnite (Rubicon Project)", "advertising", 52, True, "US"),
    ("pubmatic-zQvNh2Jk", "PubMatic", "advertising", 76, True, "US"),
    ("index-exchange-pNcBf9Wq", "Index Exchange", "advertising", 10, True, "CA"),
    ("openx-wTaYqvBG", "OpenX", "advertising", 69, True, "US"),
    ("taboola", "Taboola Europe", "advertising", 42, True, "GB"),
    ("outbrain-7Pwc8cHb", "Outbrain UK", "advertising", 164, True, "GB"),
    ("teads-kqdUJw9Y", "Teads France", "advertising", 132, True, "FR"),
    ("smartadserv-Tq3yxv7N", "Equativ (Smart AdServer)", "advertising", 45, True, "FR"),
    ("tradedesk-rGpW4LcV", "The Trade Desk", "advertising", 21, True, "US"),
    ("adform-hT7nQe2J", "Adform", "advertising", 50, True, "DK"),
    ("quantcast-5Lxd4MKb", "Quantcast", "analytics", 11, True, "US"),
    ("googleana-4TXnJigR", "Google Analytics", "analytics", None, False, "US"),
    ("hotjar-QDnRfJk8", "Hotjar", "analytics", None, False, "MT"),
    ("mixpanel-8YkLNcWq", "Mixpanel", "analytics", None, False, "US"),
    ("amplitude-mQHkL3pC", "Amplitude", "analytics", None, False, "US"),
    ("adobe-analyt-Vx2NdR6k", "Adobe Analytics", "analytics", 565, True, "US"),
    ("atinternet-fZcA8rXk", "Piano Analytics (AT Internet)", "analytics", 412, True, "FR"),
    ("contentsquare-bL7yQjt3", "Contentsquare", "analytics", None, False, "FR"),
    ("abtasty-LLkECCj8", "AB Tasty", "personalization", 576, True, "FR"),
    ("optimizely-Xcj6Hd9P", "Optimizely", "personalization", None, False, "US"),
    ("salesforce-3BqNXeGr", "Salesforce Marketing Cloud", "marketing", None, False, "US"),
    ("braze-qYjN5KxF", "Braze", "marketing", None, False, "US"),
    ("klaviyo-7nTcV4Wd", "Klaviyo", "marketing", None, False, "US"),
    ("tappx-jjy49eFA", "Tappx", "advertising", 628, True, "ES"),
    ("c:loyalty-crm", "Demo Retail loyalty CRM", "marketing", None, False, "FR"),
    ("c:zendesk", "Zendesk", "support", None, False, "US"),
    ("c:retargeting-partner", "Retargeting partner (custom)", "advertising", None, False, "DE"),
]
VENDORS = [
    {"id": v[0], "name": v[1], "category_id": v[2], "iab_id": v[3], "li": v[4], "country": v[5]} for v in _VENDORS
]
VENDOR_IDS = [v["id"] for v in VENDORS]
LI_VENDORS = [v["id"] for v in VENDORS if v["li"]]

# country -> (population weight, base opt-in rate, consent language)
COUNTRIES = {
    "FR": (25, 0.55, "FR"), "DE": (15, 0.42, "DE"), "ES": (10, 0.72, "ES"), "IT": (10, 0.68, "IT"),
    "GB": (10, 0.60, "EN"), "NL": (6, 0.48, "NL"), "BE": (5, 0.57, "FR"), "US": (9, 0.80, "EN"),
    "PL": (5, 0.70, "PL"), "SE": (5, 0.46, "SV"),
}

# primary source type -> weight
SOURCE_TYPES = {"sdk-web": 60, "sdk-mobile": 30, "api": 10}

PROPERTIES = [
    {"id": "prop-web-main", "name": "Demo Retail - main website", "website": "https://www.demo-retail.com", "country": "fr"},
    {"id": "prop-web-shop", "name": "Demo Retail - online shop", "website": "https://shop.demo-retail.com", "country": "fr"},
    {"id": "prop-web-de", "name": "Demo Retail - Germany", "website": "https://www.demo-retail.de", "country": "de"},
    {"id": "prop-web-es", "name": "Demo Retail - Spain", "website": "https://www.demo-retail.es", "country": "es"},
    {"id": "prop-pref-center", "name": "Demo Retail - preference center", "website": "https://preferences.demo-retail.com",
     "country": "fr"},
]

WEB_DOMAIN = "www.demo-retail.com"
APP_BUNDLE = "com.demoretail.app"
PREFERENCE_CENTER_DOMAIN = "preferences.demo-retail.com"
DIDOMI_CMP_ID = 7
