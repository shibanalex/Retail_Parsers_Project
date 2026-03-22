import os
from datetime import datetime

# === ИМПОРТ ВСЕХ ПАРСЕРОВ ===
#from auchan_parser import auchan
#from magnit_parser import magnit
import perekrestok
#from okey_parser import okey
#from lenta_parser import lenta
#from metro_parser import metro
#from bristol_parser import bristol
#from kib_parser import kib
#from chizhik_parser import chizhik
#from spar_parser import spar
#from pyaterochka_parser import pyaterochka
#from riat_parser import riat
#from smart_parser import smart
#from dixy_parser import dixy
#from vliga_parser import vliga
#from maxi_parser import maxi
#from globus_parser import globus
from utils import write_excel
from config import table_name, parsers #, TelegramBot
from utils import SendTelegram, SendTelegramFile


# === Папки логов и выходных файлов ===
BASE_DIR = os.getcwd() # переменная текущей папки
LOG_DIR = os.path.join(BASE_DIR, "log") # Переменная папки логов
OUTPUT_DIR = os.path.join(BASE_DIR, "output") # Переменная папки итоговых файлов
os.makedirs(LOG_DIR, exist_ok=True) # Создание папки логов
os.makedirs(OUTPUT_DIR, exist_ok=True) # Создание папки итоговых файлов

# === Словарь парсеров ===
parsers_funcs = {
    "https://perekrestok.ru/": perekrestok,
    # "https://auchan.ru/": auchan,
    # "https://lenta.com/": lenta,
    # "https://okeydostavka.ru/": okey,
    # "https://metro-cc.ru/": metro,
    # "https://online.globus.ru": globus,
    # "https://magnit.ru/": magnit,
    # "https://bristol.ru/": bristol,
    # "https://chizhik.club/": chizhik,
    # "https://myspar.ru/": spar,
    # "https://5ka.ru/": pyaterochka,
    # "https://krasnoeibeloe.ru/": kib,
    # "https://vliga.com": vliga,
    # "https://riat-market.ru/": riat,
    # "https://smart.swnn.ru/": smart,
    # "https://maxi-retail.ru/": maxi,
    # "https://dixy.ru/": dixy,
}
def write_log(message, filename):
    """Запись логов в подпапку /log/"""
    log_path = os.path.join(LOG_DIR, filename)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def start():
    all_data = []
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    # my_id   = TelegramBot.get("MY_ID")
    my_id = 1000101	

    # Формируем безопасное имя файла
    safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in table_name)

    log_filename = f"{safe_name}_{timestamp}.log"
    excel_filename = os.path.join(OUTPUT_DIR, f"MDR_{my_id}__{safe_name}_{timestamp}.xlsx")

    print(f"🚀 Running parsers...  🕐 Start time: {datetime.now().strftime('%H:%M:%S')}")
    write_log(f"=== Начало работы: {timestamp} ===", log_filename)

    for parser in parsers:
        print(f"🔹 Запуск парсера {parser}")
        # SendTelegram(f"🔹 Запуск парсера {parser}")
        func = parsers_funcs.get(parser)
        if not func:
            write_log(f"{parser}: ❌ Нет функции парсера", log_filename)
            # SendTelegram(f"{parser}: ❌ Нет функции парсера")
            continue
        try:
            parser_data = func.main()
            if parser_data:
                all_data.extend(parser_data)
#                write_log(f"{parser}: ✅ Завершён ({len(parser_data)} записей)", log_filename)
#                SendTelegram(f"{parser}: ✅ Завершён ({len(parser_data)} записей)")
                print(f"✅ Завершён : {parser}  ({len(parser_data)} записей)")
                write_log(f"✅ Завершён : {parser}  ({len(parser_data)} записей)", log_filename)
                # SendTelegram(f"✅ Завершён : {parser}  ({len(parser_data)} записей)")

            else:
                write_log(f"{parser}: ⚠️ Нет данных", log_filename)
                # SendTelegram(f"{parser}: ⚠️ Нет данных")
        except Exception as e:
            msg = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')} | Ошибка: {e} | {parser}"
            print(f"⚠️ Ошибка в {parser}: {e}")
            write_log(msg, log_filename)

    # === Сохраняем результаты ===
    if all_data:
        write_excel(all_data, excel_filename)
        write_log(f"✅ Данные сохранены: {excel_filename}", log_filename)
        print(f"✅ Результат сохранён в {excel_filename}")
        # SendTelegram(f"✅ Результат сохранён в {excel_filename}")
    else:
        write_log("⚠️ Нет данных для сохранения — Excel не создан", log_filename)
        print("⚠️ Нет данных для сохранения — Excel не создан")
        # SendTelegram("⚠️ Нет данных для сохранения — Excel не создан")

    write_log(f"=== Завершено: {datetime.now().strftime('%Y-%m-%d_%H-%M-%S')} ===", log_filename)
    print("🏁 Все парсеры завершены.")
    # SendTelegram("🏁 Все парсеры завершены.")



if __name__ == '__main__':
    start()
