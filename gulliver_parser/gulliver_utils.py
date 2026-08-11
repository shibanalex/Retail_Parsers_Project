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
    query getTopology {
      topology {
        countries {
          regions {
            cities {
              name
              defaultShop {
                id
                address
              }
            }
          }
        }
      }
    }
    """
    
    payload = {
        "operationName": "getTopology",
        "variables": {},
        "query": graphql_query
    }
    
    try:
        resp = session.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[{shop_name}] Ошибка API (HTTP {resp.status_code}) при запросе топологии.")
            return 500
            
        data = resp.json()
        countries = data.get("data", {}).get("topology", {}).get("countries", [])
        
        
        for country in countries:
            regions = country.get("regions", [])
            for region in regions:
                cities = region.get("cities", [])
                for city in cities:
                    c_name = city.get("name", "")
                    if c_name and city_lower in c_name.lower():
                        shop_info = city.get("defaultShop", {})
                        shop_id = shop_info.get("id")
                        
                        if shop_id:
                            driver.shop_id = str(shop_id)
                            
                            driver.shop_address = re.sub(r'\s+', ' ', shop_info.get("address", city_name)).strip()
                            
                            print(f"[{shop_name}] Город {c_name} найден. Привязан shop_id = {shop_id}, Адрес: {driver.shop_address}")
                            return 200
                            
        
        return 999
        
    except Exception as e:
        print(f"[{shop_name}] Ошибка загрузки топологии городов: {e}")
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
    links = []
    
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
                    "shop_id": getattr(driver, 'shop_id', "7"),
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
                print(f"[{shop_name}] Ошибка API (HTTP {resp.status_code}) на странице {page}.")
                break
                
            data = resp.json()
            search_data = data.get("data", {}).get("searchProducts", {})
            if not search_data:
                break
                
            edges = search_data.get("edges", [])
            if not edges:
                break
                
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
            
            page_info = search_data.get("pageInfo") or {}
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
        
        shop_address = getattr(driver, 'shop_address', f"{city_name} (Онлайн-каталог)")
        
        return [{
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": shop_address,
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