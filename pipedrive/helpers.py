"""
Band service skeleton
(c) Dmitry Rodin 2018
---------------------
"""
import re


def clean_phone(inp):
    return "".join(re.compile(r'[\d]+').findall(inp))
