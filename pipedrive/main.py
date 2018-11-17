"""
Band service skeleton
(c) Dmitry Rodin 2018
---------------------
"""
import asyncio
from itertools import count
from prodict import Prodict as pdict
from band import expose, worker, logger, settings
from .helpers import clean_phone
from .pipedrive import pd_query, pd_post


google_field = 'f699f454bfc8aaa65063207da2a4ddd89bd4c640'
telegram_field = '5cc799445f8401d92d2f40030900228916b0921d'
deal_course_field = 'ecc840eafa7ae6c76047f69218d7325610aee2d1'

state = pdict(
    persons=pdict(),
    stages=pdict(),
    person_fields=pdict(),
    courses=pdict(),
    deal_fields=pdict()
)


@expose()
async def course_persons(course):
    persons = []
    for person in state.persons.values():
        if course in person.courses:
            persons.append(person)
    return persons


def uniform_filter(items, field=None, val=None):
    logger.debug('uniform_filter', field=field, val=val)
    results = []
    for item in (items.values() if isinstance(items, dict) else items):
        if not field:
            results.append(item)
        else:
            prop = item.get(field, None)
            print(item, prop, val)
            if prop is not None:
                if isinstance(prop, list):
                    if val in prop:
                        results.append(item)
                else:
                    if val == prop:
                        results.append(item)
    return results


@expose()
async def filter_persons(criteria):

    field, val = [*criteria, None, None][:2]
    return uniform_filter(state.persons, field, val)


@expose()
async def get_person(criteria):
    field, val = criteria
    for person in state.persons.values():
        if person.get(field, None) == val and val is not None:
            return person


async def get_person_fields():
    res = await pd_query('personFields')
    if res and 'data' in res:
        for i in res['data']:
            state.person_fields[i['key']] = i['name']


async def get_deal_fields():
    res = await pd_query('dealFields')
    if res and 'data' in res:
        for field in res['data']:
            state.deal_fields[field['name']] = field['key']
            if field['key'] == deal_course_field:
                state.courses = {str(f['id']): f['label'] for f in field['options']}


async def get_persons():
    persons = pdict()
    res = await pd_query('persons')
    if res and 'data' in res:
        for p in res['data']:
            person = format_person(p)
            persons[person.id] = person
        state.persons.clear()
        state.persons.update(persons)


async def get_stages():
    res = await pd_query('stages')
    if res and 'data' in res:
        for stage in res['data']:
            state.stages[stage['id']] = dict(pipeline_name=stage['pipeline_name'], name=stage['name'], id=stage['id'])


async def get_deals():
    res = await pd_query('deals', {'limit': 500})
    if res and 'data' in res:
        for deal in res['data']:
            if deal[deal_course_field]:
                course_id = str(deal[deal_course_field])
                person_id = str(deal['person_id']['value'])
                if course_id and person_id and deal['person_id']['value']:
                    course = state.courses.get(course_id)
                    state.persons[person_id].courses.append(course)


@expose()
async def create_deal(data, **params):
    pd_post('deals', data)


def format_person(person):
    view = pdict(name=person['name'], courses=[], email='', phone='', phone_part='', google=person[google_field], id=str(person['id']))

    if len(person['phone']) and person['phone'][0]['value']:
        view.phone = clean_phone(person['phone'][0]['value'])
        view.phone_part = view.phone[-4:]

    if len(person['email']) and person['email'][0]['value']:
        view.email = person['email'][0]['value'].lower()
    return view


async def reload_data():
    await get_stages()
    await get_person_fields()
    await get_deal_fields()
    await get_persons()
    await get_deals()


@expose.handler()
async def deal(projectId, **params):
    if projectId == settings.projectIdKey:
        await reload_data()


@expose.handler()
async def person(projectId, **params):
    if projectId == settings.projectIdKey:
        await reload_data()


@worker()
async def service_worker():
    for num in count():
        try:
            if num == 0:
                await reload_data()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception('exc')
        await asyncio.sleep(30)
