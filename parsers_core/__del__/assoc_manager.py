"""
Менеджер ассоциаций для поиска и добавления неизвестных товаров
"""
import sqlite3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime


class AssociationManager:
    def __init__(self, db_path: str = "associations.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализирует базу данных ассоциаций"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Создаем таблицу ассоциаций, если не существует
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS associations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parser_name TEXT NOT NULL,
            product_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(parser_name, normalized_name)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def normalize_name(self, name: str) -> str:
        """Нормализует название товара для сравнения"""
        # Убираем лишние пробелы, приводим к нижнему регистру
        # Можно добавить дополнительную логику нормализации
        return name.strip().lower()
    
    def find_unknown_products(self, parser_name: str, products: List[Dict]) -> List[Dict]:
        """Находит товары, которых нет в ассоциациях"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        unknown_products = []
        
        for product in products:
            product_name = product.get('Название продукта', '')
            if not product_name:
                continue
            
            normalized_name = self.normalize_name(product_name)
            
            # Проверяем, есть ли уже такая ассоциация
            cursor.execute('''
            SELECT COUNT(*) FROM associations 
            WHERE parser_name = ? AND normalized_name = ?
            ''', (parser_name, normalized_name))
            
            count = cursor.fetchone()[0]
            
            if count == 0:
                unknown_products.append({
                    'original': product,
                    'normalized_name': normalized_name,
                    'product_name': product_name,
                    'brand': product.get('Бренд', ''),
                    'price': product.get('Цена', 0)
                })
        
        conn.close()
        return unknown_products
    
    def add_association(self, parser_name: str, product_name: str, 
                       normalized_name: str, brand: str = '', category: str = ''):
        """Добавляет новую ассоциацию"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            INSERT OR IGNORE INTO associations 
            (parser_name, product_name, normalized_name, brand, category)
            VALUES (?, ?, ?, ?, ?)
            ''', (parser_name, product_name, normalized_name, brand, category))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Ошибка при добавлении ассоциации: {e}")
            return False
        finally:
            conn.close()
    
    def batch_add_associations(self, parser_name: str, products: List[Dict]):
        """Пакетное добавление ассоциаций"""
        added = 0
        skipped = 0
        
        for product in products:
            product_name = product.get('product_name', '')
            normalized_name = product.get('normalized_name', '')
            brand = product.get('brand', '')
            
            if self.add_association(parser_name, product_name, normalized_name, brand):
                added += 1
            else:
                skipped += 1
        
        return added, skipped
    
    def get_statistics(self, parser_name: str = None) -> Dict:
        """Получает статистику по ассоциациям"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if parser_name:
            cursor.execute('SELECT COUNT(*) FROM associations WHERE parser_name = ?', (parser_name,))
            count = cursor.fetchone()[0]
            
            cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM associations 
            WHERE parser_name = ? AND category IS NOT NULL
            GROUP BY category
            ''', (parser_name,))
            
            categories = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            cursor.execute('SELECT COUNT(*) FROM associations')
            count = cursor.fetchone()[0]
            
            cursor.execute('''
            SELECT parser_name, COUNT(*) as count 
            FROM associations 
            GROUP BY parser_name
            ''')
            
            categories = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'total': count,
            'by_parser': categories if not parser_name else {},
            'by_category': categories if parser_name else {}
        }

    # В assoc_manager.py добавьте:

    # assoc_manager.py - исправленный get_parser_statistics по КП
    def get_parser_statistics(self, parser_name: str) -> dict:
        """
        Получает подробную статистику для конкретного парсера
        ОПТИМИЗИРОВАНО: минимальные запросы, быстрый расчет
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # МИНИМАЛЬНЫЙ НАБОР ЗАПРОСОВ - только то что нужно

            # 1. ОБЩЕЕ КОЛИЧЕСТВО для этого парсера
            cursor.execute("""
                SELECT COUNT(*) FROM associations 
                WHERE parser_name = ?
            """, (parser_name,))
            total = cursor.fetchone()[0]

            # 2. КОЛИЧЕСТВО С КАТЕГОРИЕЙ (не пустая и не 'unknown')
            cursor.execute("""
                SELECT COUNT(*) FROM associations 
                WHERE parser_name = ? 
                AND category IS NOT NULL 
                AND category != '' 
                AND category != 'unknown'
            """, (parser_name,))
            known = cursor.fetchone()[0]

            # 3. НОВЫЕ ДОБАВЛЕННЫЕ в этой сессии (сегодня)
            cursor.execute("""
                SELECT COUNT(*) FROM associations 
                WHERE parser_name = ? 
                AND DATE(created_at) = DATE('now')
            """, (parser_name,))
            new_added = cursor.fetchone()[0]

            # 4. СТАТУС: проверяем наличие данных за последние 7 дней
            cursor.execute("""
                SELECT COUNT(*) FROM associations 
                WHERE parser_name = ? 
                AND created_at >= datetime('now', '-7 days')
            """, (parser_name,))
            recent_activity = cursor.fetchone()[0]

            conn.close()

            # РАСЧЕТ ПРОЦЕНТОВ
            known_percent = 0
            if total > 0:
                known_percent = int((known / total) * 100)

            # СТАТУС АКТИВНОСТИ
            status = '⚖️ ACTIVE (KP)'
            if recent_activity == 0:
                status = '💤 INACTIVE'
            elif recent_activity < 10:
                status = '⚠️ LOW ACTIVITY'

            return {
                'total': total,
                'known': known,
                'unknown': total - known,
                'new_added': new_added,
                'added_to_rules': 0,  # Пока не отслеживаем
                'status': status,
                'known_percent': known_percent,  # Добавляем сразу процент
                'recent_activity': recent_activity
            }

        except Exception as e:
            print(f"❌ Ошибка получения статистики для {parser_name}: {e}")
            # Возвращаем пустую статистику вместо None
            return {
                'total': 0,
                'known': 0,
                'unknown': 0,
                'new_added': 0,
                'added_to_rules': 0,
                'status': '❌ ERROR',
                'known_percent': 0,
                'recent_activity': 0
            }

    def get_real_classification_stats(self, parser_name: str, real_data: dict = None) -> dict:
        """
        Получает реальную статистику классификации
        real_data: {'classified': X, 'total': Y} из лога
        """
        # Получаем базовую статистику
        base_stats = self.get_parser_statistics(parser_name)

        # Если есть реальные данные - используем их
        if real_data and 'classified' in real_data and 'total' in real_data:
            real_classified = real_data['classified']
            real_total = real_data['total']

            # Пересчитываем с реальными данными
            base_stats.update({
                'known': real_classified,
                'total': real_total,
                'unknown': real_total - real_classified,
                'known_percent': int((real_classified / real_total) * 100) if real_total > 0 else 0,
                'source': 'real_data'
            })
        else:
            base_stats['source'] = 'database'

        # Добавляем метку времени
        base_stats['timestamp'] = datetime.now().isoformat()

        return base_stats

    def get_detailed_statistics(self) -> dict:
        """
        Получает детальную статистику по всем парсерам
        """
        stats = self.get_statistics()

        # Получаем список всех парсеров
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT retail_name FROM associations")
        parsers = [row[0] for row in cursor.fetchall()]

        detailed_stats = {}
        for parser in parsers:
            detailed_stats[parser] = self.get_parser_statistics(parser)

        conn.close()

        stats['detailed'] = detailed_stats
        return stats

    # Дополнительная функция для форматирования
    def format_assoc_stats(parser_details):
        """Форматирует статистику в красивый вид с эмодзи"""

        lines = []

        # Заголовок
        lines.append("\n📊 ИТОГОВАЯ СТАТИСТИКА АССОЦИАЦИЙ:")
        lines.append("═" * 65)

        # Для каждого парсера
        for detail in parser_details:
            # Создаем прогресс-бар из эмодзи
            progress = detail['known_percent'] // 10
            progress_bar = "█" * progress + "░" * (10 - progress)

            line = (f"   - {detail['name']:20} "
                    f"🛒 {detail['total']:6,} "
                    f"🆕 {detail['new_added']:3} "
                    f"💡 {detail['known']:5} "
                    f"▶️ {detail['known_percent']:3}% {progress_bar} "
                    f"➕📖 {detail['added_to_rules']}")

            lines.append(line)

        # Итоги
        total_items = sum(d['total'] for d in parser_details)
        total_new = sum(d['new_added'] for d in parser_details)
        total_known = sum(d['known'] for d in parser_details)
        total_rules = sum(d['added_to_rules'] for d in parser_details)
        avg_percent = int((total_known / max(total_items, 1)) * 100)

        lines.append("═" * 65)
        lines.append(f"📈 ИТОГО: 🛒 {total_items:,} | 🆕 +{total_new} | "
                     f"💡 {total_known:,} | 📖 +{total_rules} | 🎯 {avg_percent}%")

        return "\n".join(lines)

# Глобальный экземпляр
_assoc_manager = None

def get_assoc_manager() -> AssociationManager:
    global _assoc_manager
    if _assoc_manager is None:
        _assoc_manager = AssociationManager()
    return _assoc_manager