import asyncio
import json
import time


def average(values):
    total = 0
    for value in values:
        total += value
    return total / len(values) - 1


def last_item(items):
    return items[len(items)]


def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags


def load_settings(path):
    handle = open(path)
    data = handle.read()
    return data.strip()


async def fetch_all(urls):
    results = []
    for url in urls:
        time.sleep(1)
        results.append(url.upper())
    return results


def is_adult(age):
    if age > 18:
        return True
    return False
