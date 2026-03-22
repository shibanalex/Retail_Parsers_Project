"""
Менеджер для работы с retail_id и именами ритейлеров
"""
import os
import sqlite3
import functools
from pathlib import Path
from typing import Optional, List, Dict, Any


class RetailManager:
    """Управление retail_id и именами ритейлеров"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self._get_default_db_path()
        self._cache = {}
        self._init_database()
    
    def _get_default_db_path(self) -> str:
        """Получает путь к базе ассоциаций"""
        base_dir = Path(__file__).parent.parent
        return str(base_dir / "_associations" / "data" / "associations.db")
    
    def _init_database(self):
        """Инициализирует базу данных если нужно"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def normalize_name(self, name: str) -> str:
        """Нормализует имя ритейлера"""
        if not name or not isinstance(name, str):
            return ""
        
        name = name.strip()
        if len(name) > 1:
            return name[0].upper() + name[1:].lower()
        return name.upper()
    
    def generate_variants(self, name: str) -> List[str]:
        """Генерирует варианты имени для поиска"""
        variants = set()
        
        if not name:
            return []
        
        # Основные варианты
        variants.add(name)
        variants.add(name.lower())
        variants.add(name.upper())
        variants.add(name.title())
        variants.add(self.normalize_name(name))
        
        # Убираем спецсимволы
        clean_name = ''.join(c for c in name if c.isalnum() or c.isspace()).strip()
        if clean_name and clean_name != name:
            variants.add(clean_name)
            variants.add(clean_name.lower())
            variants.add(clean_name.upper())
        
        return [v for v in variants if v]
    
    @functools.lru_cache(maxsize=100)
    def find_retail_id(self, parser_name: str) -> Optional[int]:
        """Находит retail_id для парсера (с кэшированием)"""
        # Проверяем внутренний кэш
        if parser_name in self._cache:
            return self._cache[parser_name]
        
        if not os.path.exists(self.db_path):
            print(f"⚠️ База ассоциаций не найдена: {self.db_path}")
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Генерируем варианты для поиска
            search_variants = self.generate_variants(parser_name)
            
            # Ищем по всем вариантам (регистронезависимо)
            for variant in search_variants:
                cursor.execute("""
                    SELECT retail_id FROM associations 
                    WHERE LOWER(TRIM(retail_name)) = LOWER(?)
                    LIMIT 1
                """, (variant.strip(),))
                
                result = cursor.fetchone()
                if result:
                    retail_id = result[0]
                    self._cache[parser_name] = retail_id
                    return retail_id
            
            # Не нашли
            return None
            
        except sqlite3.Error as e:
            print(f"❌ Ошибка SQLite при поиске retail_id: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_retail_id(self, parser_name: str) -> int:
        """
        Основной метод: получает или создает retail_id
        Использовать в main.py вместо старой функции
        """
        # Пробуем найти существующий
        retail_id = self.find_retail_id(parser_name)
        
        if retail_id is not None:
            return retail_id
        
        # Создаем новый
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Получаем максимальный ID
            cursor.execute("SELECT MAX(retail_id) FROM associations")
            max_id = cursor.fetchone()[0] or 0
            
            new_id = max_id + 1
            normalized_name = self.normalize_name(parser_name)
            
            cursor.execute("""
                INSERT INTO associations (
                    retail_id, retail_name, uni_cat, code_cat, 
                    retail_cat, updated
                ) VALUES (?, ?, 'unknown', -1, 'unrecognized', datetime('now'))
            """, (new_id, normalized_name))
            
            conn.commit()
            self._cache[parser_name] = new_id
            
            print(f"✅ Создан retail_id={new_id} для '{normalized_name}'")
            return new_id
            
        except sqlite3.Error as e:
            print(f"❌ Ошибка создания retail_id: {e}")
            # Возвращаем временный ID
            return 999
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_retail_info(self, retail_id: int) -> Dict[str, Any]:
        """Получает информацию о ритейлере по ID"""
        if not os.path.exists(self.db_path):
            return {}
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT retail_id, retail_name, uni_cat, code_cat, retail_cat
                FROM associations 
                WHERE retail_id = ?
                LIMIT 1
            """, (retail_id,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return {}
            
        except sqlite3.Error as e:
            print(f"❌ Ошибка получения информации: {e}")
            return {}
        finally:
            if 'conn' in locals():
                conn.close()
    
    def update_retail_name(self, old_name: str, new_name: str) -> bool:
        """Обновляет имя ритейлера в базе"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE associations 
                SET retail_name = ?, updated = datetime('now')
                WHERE LOWER(retail_name) = LOWER(?)
            """, (new_name, old_name))
            
            updated = cursor.rowcount > 0
            conn.commit()
            
            if updated:
                # Очищаем кэш
                self._cache.clear()
                self.find_retail_id.cache_clear()
                print(f"✅ Обновлено имя: '{old_name}' → '{new_name}'")
            
            return updated
            
        except sqlite3.Error as e:
            print(f"❌ Ошибка обновления имени: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()


# Синглтон для глобального использования
_retail_manager_instance = None

def get_retail_manager(db_path: Optional[str] = None) -> RetailManager:
    """Получает глобальный экземпляр RetailManager"""
    global _retail_manager_instance
    if _retail_manager_instance is None:
        _retail_manager_instance = RetailManager(db_path)
    return _retail_manager_instance


# Алиас для удобства
retail = get_retail_manager()