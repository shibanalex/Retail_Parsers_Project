import time
from pyaterochka_parser.five_get_items_data import get_all_data


def main():
    start = time.time()
    all_data = get_all_data()
    finish = time.time()
    print(f"Время работы парсера: {(finish - start) / 60:.2f} минут.")
    return all_data


if __name__ == "__main__":
    main()
