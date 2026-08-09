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
    
    
    payload = {
        "operationName": "getTopology",
        "variables": {},
        "query": "query getTopology {\n  topology {\n    countries {\n      regions {\n        cities {\n          name\n          defaultShop {\n            id\n          }\n        }\n      }\n    }\n  }\n}"
    }

    try:
        resp = session.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            countries = data.get("data", {}).get("topology", {}).get("countries", [])
            
            
            for country in countries:
                for region in country.get("regions", []):
                    for city in region.get("cities", []):
                        current_city_name = city.get("name", "").lower().strip()
                        
                        
                        if current_city_name == city_lower or city_lower in current_city_name:
                            shop_id = city.get("defaultShop", {}).get("id")
                            if shop_id:
                                driver.shop_id = str(shop_id)
                                print(f"[{shop_name}] Город '{city.get('name')}' успешно определен (shop_id: {shop_id}).")
                                return 200
                                
            print(f"[{shop_name}] Ошибка 999. Город '{city_name}' не найден в зоне доставки Гулливер.")
            return 999
        else:
            print(f"[{shop_name}] Ошибка получения списка городов (HTTP {resp.status_code}).")
            return 500
    except Exception as e:
        print(f"[{shop_name}] Ошибка API при поиске города: {e}")
        return 500

def extract_volume_weight(name, pkg):
    weight, volume = "", ""
    txt_lower = f"{name} {pkg}".lower()
    
    w_match = re.search(r'(\d+[.,]?\d*)\s*(г|кг)\b', txt_lower)
    if w_match: weight = w_match.group(0)
        
    v_match = re.search(r'(\d+[.,]?\d*)\s*(мл|л)\b', txt_lower)
    if v_match: volume = v_match.group(0)
        
    return volume, weight

def get_product_links(driver, query, shop_name):
    global _cached_catalog_products
    session = driver.session
    links = []
    
    
    shop_id = getattr(driver, 'shop_id', "7")
    
    url = "https://backend-v2.shop.gulliver-ul.ru/api/v1.1/customer/graph?platform=web&dt=web&av=4.1.0"
    
    page = 1
    limit = 20 
    
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
        pageInfo {
          page
          lastPage
        }
      }
    }
    """

    try:
        while len(links) < MAX_PRODUCTS_PER_QUERY:
            payload = {
                "operationName": "searchProducts",
                "variables": {
                    "shop_id": shop_id,
                    "page": page,
                    "limit": limit,
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
                print(f"[{shop_name}] Ошибка API поиска (HTTP {resp.status_code}) на странице {page}.")
                break
                
            data = resp.json()
            search_data = data.get("data", {}).get("searchProducts", {})
            edges = search_data.get("edges", [])
            
            if not edges:
                break
                
            for item in edges:
                slug = item.get("slug")
                if not slug: continue
                
                prod_url = f"https://gulliver-ul.ru/product/{slug}"
                name = item.get("name", "Неизвестный товар")
                
                brand = item.get("brand", {})
                brand_name = brand.get("name", "") if brand else ""
                
                stock_data = item.get("stock", {})
                stock_amount = stock_data.get("amount", 0) if stock_data else 0
                
                
                price_base = 0.0
                price_promo = None
                offers = item.get("priceOffers", [])
                
                if offers:
                    offer = offers[0]
                    p_current = float(offer.get("price", 0) or 0)
                    p_old = float(offer.get("oldPrice", 0) or 0)
                    
                    if p_old > p_current:
                        price_base = p_old
                        price_promo = p_current
                    else:
                        price_base = p_current
                        
                photo = ""
                preview = item.get("preview", {})
                if preview:
                    photo = preview.get("url", "")
                    
                rating = item.get("average_rating")
                rating = float(rating) if rating else None
                
                gtin = item.get("xid", "")
                
                pkg = item.get("pkg", "")
                volume, weight = extract_volume_weight(name, pkg)
                
                _cached_catalog_products[prod_url] = {
                    "Название продукта": name,
                    "Цена": price_base,
                    "Цена по акции": price_promo,
                    "Остаток": int(stock_amount),
                    "Рейтинг": rating,
                    "Фото товара": photo,
                    "Бренд": brand_name,
                    "GTIN": gtin,
                    "Объем": volume,
                    "Вес": weight
                }
                
                links.append(prod_url)
                if len(links) >= MAX_PRODUCTS_PER_QUERY:
                    break
            
            
            page_info = search_data.get("pageInfo", {})
            current_page = page_info.get("page", page)
            last_page = page_info.get("lastPage", page)
            
            if current_page >= last_page:
                break
                
            page += 1
            smart_sleep(driver, 1.5)

        print(f"[{shop_name}] Найдено {len(links)} товаров через GraphQL API.")
        return links
        
    except Exception as e:
        print(f"[{shop_name}] Ошибка API поиска '{query}': {e}")
        return []

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    global _cached_catalog_products
    
    
    if product_url in _cached_catalog_products:
        c = _cached_catalog_products[product_url]
        return [{
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": f"{city_name} (Интернет-магазин / Доставка)",
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
        }]
        
    return []