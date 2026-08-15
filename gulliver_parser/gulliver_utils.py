import time
import random
import re


MAX_PRODUCTS_PER_QUERY = 100
_cached_catalog_products = {}

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(driver, shop_name):
    return True

def set_city(driver, city_name, shop_name):
    global _cached_catalog_products
    _cached_catalog_products = {}
    session = driver.session
    
    city_lower = city_name.lower().strip()
    url = "https://backend-v2.shop.gulliver-ul.ru/api/v1.1/customer/graph?platform=web&dt=web&av=4.1.0"
    
    
    graphql_query = """
    query shopsInGeoPolygon($corners: [GeoPointInput]!, $useZone: Boolean, $style: String, $shopImageStyle: String, $iconStyle: String, $customerType: String) {
      shopsInGeoPolygon(corners: $corners, useZone: $useZone, customerType: $customerType) {
        id
        name
        address
        status
      }
    }
    """
    
    payload = {
        "operationName": "shopsInGeoPolygon",
        "variables": {
            "corners": [
                {"latitude": -90, "longitude": -180},
                {"latitude": -90, "longitude": 180},
                {"latitude": 90, "longitude": 180},
                {"latitude": 90, "longitude": -180}
            ]
        },
        "query": graphql_query
    }
    
    try:
        resp = session.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[{shop_name}] Ошибка API (HTTP {resp.status_code}) при запросе всех магазинов.")
            return 500
            
        data = resp.json()
        shops = data.get("data", {}).get("shopsInGeoPolygon", [])
        
        
        driver.city_shops = []
        for shop in shops:
            addr = shop.get("address", "")
            if city_lower in addr.lower():
                driver.city_shops.append({
                    "id": str(shop.get("id")),
                    "address": re.sub(r'\s+', ' ', addr).strip() 
                })
                
        if not driver.city_shops:
            print(f"[{shop_name}] Магазины для города {city_name} не найдены.")
            return 999
            
        print(f"[{shop_name}] Город {city_name} установлен. Найдено {len(driver.city_shops)} магазинов сети.")
        return 200
        
    except Exception as e:
        print(f"[{shop_name}] Ошибка загрузки топологии магазинов: {e}")
        return 500

def extract_volume_weight(name, pkg):
    weight, volume = "", ""
    name_str = str(name) if name else ""
    pkg_str = str(pkg) if pkg else ""
    
    txt_lower = f"{name_str} {pkg_str}".lower()
    
    w_match = re.search(r'(\d+[.,]?\d*)\s*(г|кг)\b', txt_lower)
    if w_match: weight = w_match.group(0)
        
    v_match = re.search(r'(\d+[.,]?\d*)\s*(мл|л)\b', txt_lower)
    if v_match: volume = v_match.group(0)
        
    return volume, weight

def get_product_links(driver, query, shop_name):
    global _cached_catalog_products
    session = driver.session
    links = set()
    
    url = "https://backend-v2.shop.gulliver-ul.ru/api/v1.1/customer/graph?platform=web&dt=web&av=4.1.0"
    
    graphql_query = """
    query searchProducts($shop_id: ID!, $searchQuery: SearchQuery!, $filter: NestedFilterInput, $style: String, $page: Int, $limit: Int) {
      searchProducts(shop_id: $shop_id, searchQuery: $searchQuery, filter: $filter, _page: $page, _limit: $limit) {
        edges {
          id
          xid
          name
          slug
          weight
          pkg
          brand {
            id
            name
          }
          preview(style: $style) {
            url
          }
          review_count
          average_rating
          stock {
            amount
          }
          priceOffers {
            price
            oldPrice
          }
        }
      }
    }
    """

    try:
        
        for shop in getattr(driver, 'city_shops', []):
            shop_id = shop["id"]
            shop_addr = shop["address"]
            
            payload = {
                "operationName": "searchProducts",
                "variables": {
                    "shop_id": shop_id,
                    "page": 1,
                    "limit": MAX_PRODUCTS_PER_QUERY,
                    "searchQuery": {
                        "search": query,
                        "filters": {}
                    },
                    "filter": {
                        "and": []
                    }
                },
                "query": graphql_query
            }

            resp = session.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                continue
                
            data = resp.json()
            search_data = data.get("data", {}).get("searchProducts", {})
            if not search_data:
                continue
                
            edges = search_data.get("edges", [])
            
            for item in edges:
                slug = item.get("slug")
                if not slug: continue
                
                prod_url = f"https://gulliver-ul.ru/product/{slug}"
                name = item.get("name", "Неизвестный товар")
                
                brand = item.get("brand") or {}
                brand_name = brand.get("name", "")
                
                stock_data = item.get("stock") or {}
                stock_amount = stock_data.get("amount", 0)
                
                price_base = 0.0
                price_promo = None
                offers = item.get("priceOffers") or []
                
                if offers:
                    offer = offers[0]
                    p_current = float(offer.get("price") or 0)
                    p_old = float(offer.get("oldPrice") or 0)
                    
                    if p_old > p_current:
                        price_base = p_old
                        price_promo = p_current
                    else:
                        price_base = p_current
                        
                photo = ""
                preview = item.get("preview") or {}
                if preview:
                    photo = preview.get("url", "")
                    
                rating = item.get("average_rating")
                rating = float(rating) if rating else None
                
                gtin = item.get("xid", "")
                pkg = item.get("pkg", "")
                
                volume, weight = extract_volume_weight(name, pkg)
                
                links.add(prod_url)
                
                
                if prod_url not in _cached_catalog_products:
                    _cached_catalog_products[prod_url] = {}
                    
                _cached_catalog_products[prod_url][shop_id] = {
                    "Название продукта": name,
                    "Цена": price_base,
                    "Цена по акции": price_promo,
                    "Остаток": int(stock_amount),
                    "Рейтинг": rating,
                    "Фото товара": photo,
                    "Бренд": brand_name,
                    "GTIN": gtin,
                    "Объем": volume,
                    "Вес": weight,
                    "Адрес Торговой точки": shop_addr
                }
                
            smart_sleep(driver, 0.5)

        print(f"[{shop_name}] Найдено {len(links)} уникальных товаров.")
        return list(links)
        
    except Exception as e:
        print(f"[{shop_name}] Ошибка API поиска '{query}': {e}")
        return []

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    global _cached_catalog_products
    results = []
    
    if product_url in _cached_catalog_products:
        shop_data_map = _cached_catalog_products[product_url]
        
        
        for shop_id, c in shop_data_map.items():
            results.append({
                "Номер": 0,
                "Сеть": retail_name,
                "Тип магазина": "Магазин",
                "Адрес Торговой точки": c["Адрес Торговой точки"],
                "Бренд": c["Бренд"], 
                "Название продукта": c["Название продукта"],
                "Цена": c["Цена"],
                "Цена по акции": c["Цена по акции"],
                "Фото товара": c["Фото товара"],
                "Ссылка на страницу": product_url,
                "Рейтинг": c["Рейтинг"],
                "Объем": c["Объем"],
                "Вес": c["Вес"],
                "Остаток": c["Остаток"],
                "GTIN": c["GTIN"]
            })
            
    return results