import os as _os

site_url = "https://www.perekrestok.ru/"
city_url = "https://www.perekrestok.ru/api/customer/1.4.1.0/delivery/mode/pickup/"
product_url = "https://www.perekrestok.ru/api/customer/1.4.1.0/catalog/product/"
category_items_url = "https://www.perekrestok.ru/api/customer/1.4.1.0/catalog/product/grouped-feed"
brand_url = "https://www.perekrestok.ru/api/customer/1.4.1.0/catalog/search/enums/tip-produkta"

_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
json_path = _os.path.join(_PROJECT_ROOT, "output", "items_data_by_")
