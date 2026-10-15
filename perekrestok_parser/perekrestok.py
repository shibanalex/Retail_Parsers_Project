import time
from perekrestok_parser.get_items_data import get_search
from parsers_core.utils import SendTelegram, SendTelegramFile
 
 
def main():
    start = time.time()
    all_data = get_search()
    finish = time.time()
    print(f"Время работы парсера: {(finish - start) / 60:.2f} минут.")

    return all_data
 
if __name__ == "__main__":
    main()
