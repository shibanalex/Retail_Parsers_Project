# -*- coding: utf-8 -*-


class NoShopsError(Exception):
    def __init__(self, parser_name, city):
        self.parser_name = parser_name
        self.city = city
        super().__init__(f"{parser_name}: нет торговых точек в городах: {city}")


class RateLimited(Exception):
    pass


class AuthLost(Exception):
    pass
