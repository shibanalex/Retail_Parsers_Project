import time
#import sys
#import os
#sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # корень OUT
#from get_items_data import get_search, get_all_data, get_item_data
from perekrestok_parser.get_items_data import get_search
from parsers_core.utils import SendTelegram, SendTelegramFile
 
 
def main():
    start = time.time()
    all_data = get_search()
    finish = time.time()
    print(f"Время работы парсера: {(finish - start) / 60:.2f} минут.")
    # SendTelegram(f"✅ <b>Парсер Перекресток завершён успешно!</b>\n🏁 Время: {(finish - start) / 60:.2f} минут.")
 
    return all_data
 
if __name__ == "__main__":
    main()
