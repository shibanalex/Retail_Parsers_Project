"""
Модуль для сохранения данных для оффлайн-обучения ассоциаций
"""
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import traceback


class AssocFileSaver:
    """Сохранение данных для оффлайн-обучения ассоциаций"""
    
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.save_dir = self.base_dir / "debug" / "assoc_offline"
        self.save_dir.mkdir(parents=True, exist_ok=True)
    
    def save_for_training(self, 
                         parser_name: str, 
                         data: List[Dict], 
                         metadata: Dict = None) -> str:
        """
        Сохраняет массив данных для оффлайн-обучения
        
        Args:
            parser_name: Имя парсера
            data: Массив данных (тот же, что передается в assoc)
            metadata: Дополнительные метаданные
        
        Returns:
            Путь к сохраненному файлу
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"assoc_train_{parser_name}_{timestamp}.json"
            filepath = self.save_dir / filename
            
            # Подготовка данных
            save_data = {
                "parser_name": parser_name,
                "timestamp": timestamp,
                "count": len(data),
                "data": data,
                "metadata": metadata or {},
                "file_created": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            # Сохраняем в JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"💾 Данные для обучения сохранены: {filepath}")
            print(f"   • Парсер: {parser_name}")
            print(f"   • Записей: {len(data)}")
            
            return str(filepath)
            
        except Exception as e:
            print(f"❌ Ошибка сохранения данных: {e}")
            traceback.print_exc()
            return ""
    
    def save_raw_data(self, 
                     parser_name: str, 
                     raw_data: List[Dict],
                     processed_data: List[Dict] = None) -> str:
        """
        Сохраняет сырые и обработанные данные для сравнения
        
        Args:
            parser_name: Имя парсера
            raw_data: Сырые данные парсера
            processed_data: Данные после адаптера
        
        Returns:
            Путь к сохраненному файлу
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"assoc_raw_{parser_name}_{timestamp}.json"
            filepath = self.save_dir / filename
            
            save_data = {
                "parser_name": parser_name,
                "timestamp": timestamp,
                "raw_count": len(raw_data),
                "processed_count": len(processed_data) if processed_data else 0,
                "raw_sample": raw_data[:3] if raw_data else [],  # Первые 3 для примера
                "processed_sample": processed_data[:3] if processed_data else [],
                "raw_keys": list(raw_data[0].keys()) if raw_data else [],
                "file_created": datetime.now().isoformat()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"📄 Сырые данные сохранены: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"❌ Ошибка сохранения сырых данных: {e}")
            return ""
    
    def load_training_data(self, filepath: str) -> Dict:
        """Загружает данные из файла обучения"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Ошибка загрузки файла {filepath}: {e}")
            return {}
    
    def list_training_files(self, parser_name: str = None) -> List[str]:
        """Список файлов для обучения"""
        pattern = "assoc_train_*.json" if parser_name is None else f"assoc_train_{parser_name}_*.json"
        files = []
        for file in self.save_dir.glob(pattern):
            files.append(str(file))
        return sorted(files)
    
    def list_raw_files(self, parser_name: str = None) -> List[str]:
        """Список файлов с сырыми данными"""
        pattern = "assoc_raw_*.json" if parser_name is None else f"assoc_raw_{parser_name}_*.json"
        files = []
        for file in self.save_dir.glob(pattern):
            files.append(str(file))
        return sorted(files)
    
    def get_latest_file(self, parser_name: str = None) -> Optional[str]:
        """Получает самый свежий файл"""
        files = self.list_training_files(parser_name)
        return files[-1] if files else None
    
    def get_file_info(self, filepath: str) -> Dict:
        """Информация о файле"""
        try:
            data = self.load_training_data(filepath)
            return {
                "parser": data.get("parser_name", "unknown"),
                "records": data.get("count", 0),
                "timestamp": data.get("timestamp", ""),
                "created": data.get("file_created", ""),
                "file_size": os.path.getsize(filepath)
            }
        except:
            return {}
    
    def analyze_data(self, filepath: str) -> Dict:
        """Анализирует данные в файле"""
        data = self.load_training_data(filepath)
        if not data:
            return {}
        
        records = data.get("data", [])
        if not records:
            return {"error": "Нет данных"}
        
        # Статистика по полям
        field_stats = {}
        for record in records:
            for key, value in record.items():
                if key not in field_stats:
                    field_stats[key] = {"count": 0, "types": set()}
                field_stats[key]["count"] += 1
                field_stats[key]["types"].add(type(value).__name__)
        
        # Преобразуем типы в строки
        for key in field_stats:
            field_stats[key]["types"] = list(field_stats[key]["types"])
        
        return {
            "total_records": len(records),
            "fields": field_stats,
            "sample_record": records[0] if records else {}
        }
    
    def clear_old_files(self, days_old: int = 30):
        """Удаляет старые файлы"""
        cutoff_time = datetime.now().timestamp() - (days_old * 24 * 3600)
        deleted = 0
        
        for file in self.save_dir.glob("*.json"):
            if file.stat().st_mtime < cutoff_time:
                try:
                    file.unlink()
                    deleted += 1
                except Exception as e:
                    print(f"❌ Не удалось удалить {file}: {e}")
        
        if deleted:
            print(f"🗑️ Удалено {deleted} старых файлов (старше {days_old} дней)")


# Глобальный экземпляр
_assoc_saver_instance = None

def get_assoc_saver() -> AssocFileSaver:
    """Получает глобальный экземпляр AssocFileSaver"""
    global _assoc_saver_instance
    if _assoc_saver_instance is None:
        _assoc_saver_instance = AssocFileSaver()
    return _assoc_saver_instance


# Алиас для удобства
assoc_saver = get_assoc_saver()