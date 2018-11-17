
import aiohttp
from band import settings, logger


async def api_call(url, params=None, json=None, method='get'):
    async with aiohttp.ClientSession() as session:
        method = getattr(session, method.lower())
        async with method(url, json=json, params=params) as res:
            logger.debug(f'quering {url}', status=res.status)
            if res.status == 204:
                return {}
            if res.status == 200:
                return await res.json()


def filter_query(filter_id):
    return {'filter_id': filter_id, **auth_query()}


def auth_query(dict_={}):
    return {'api_token': settings.api_token, **dict_}


async def pd_query(service, params={}):
    url = settings.endpoint + service
    params = auth_query(params)
    return await api_call(url, params=params)


async def pd_post(service, data, params={}):
    url = settings.endpoint + service
    params = auth_query(params)
    return await api_call(url, params=params, json=data)
