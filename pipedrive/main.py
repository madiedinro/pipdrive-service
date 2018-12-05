"""
Band service skeleton
(c) Dmitry Rodin 2018
---------------------
"""
import asyncio
from itertools import count
from prodict import Prodict as pdict
from band import expose, worker, logger, settings, scheduler
from pprint import pprint
from .helpers import clean_phone
from .pipedrive import pd_query, pd_post


class state:
    persons = pdict()
    stages = pdict()
    deals = pdict()
    person_fields = pdict()
    deal_fields = pdict()


def prepare_field(field):
    res = {
        'key': field['name'].lower()
    }
    if 'options' in field:
        res['options'] = {str(f['id']): f['label'] for f in field['options']}
    return res


def fix_struct(item, fields):
    for k, val in [*item.items()]:
        if len(k) == 40 and k in fields:
            field = fields[k]
            fk = field['key']
            item[fk] = val
            if 'options' in field and val:
                item[fk] = field['options'][str(val)]
    return item

@expose()
async def filter_persons(criteria):
    field, val = [*criteria, None, None][:2]
    return uniform_filter(state.persons, field, val)


@expose()
async def course_persons(course):
    persons = []
    for person in state.persons.values():
        if course in person.courses:
            persons.append(person)
    return persons


@expose()
async def get_person(criteria):
    field, val = criteria
    persons = uniform_filter(state.persons, field, val)
    return persons[0] if len(persons) else None


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
                if isinstance(prop, list) or isinstance(prop, set):
                    if val in prop:
                        results.append(item)
                else:
                    if val == prop:
                        results.append(item)
    return results


async def load_person_fields():
    res = await pd_query('personFields')
    if res and 'data' in res:
        state.person_fields = {i['key'].lower(): prepare_field(i) for i in res['data'] if len(i['key']) == 40}


async def load_deal_fields():
    res = await pd_query('dealFields')
    if res and 'data' in res:
        state.deal_fields = {i['key'].lower(): prepare_field(i) for i in res['data'] if len(i['key']) == 40}


async def load_stages():
    res = await pd_query('stages')
    if res and 'data' in res:
        state.stages.clear()
        for stage in res['data']:
            state.stages[stage['id']] = dict(pipeline_name=stage['pipeline_name'], name=stage['name'], id=stage['id'])


async def load_persons():
    res = await pd_query('persons', {'limit': 500})
    if res and 'data' in res:
        state.persons.clear()
        for p in res['data']:
            pers_id = str(p['id'])
            state.persons[pers_id] = format_person(fix_struct(p, state.person_fields))


async def load_deals():
    res = await pd_query('deals', {'limit': 500})
    if res and 'data' in res:
        state.deals.clear()
        for deal in res['data']:
            pers_id = deal['person_id']['value'] = str(deal['person_id']['value'])
            state.deals[deal['id']] = fix_struct(deal, state.deal_fields)
            if deal.get('course', None) and deal.get('status', None) in ['open', 'won']:
                state.persons[pers_id].courses.add(deal['course'])
        logger.warn('deal', deal)
            # if deal[deal_course_field]:
            #     course_id = str(deal[deal_course_field])
            #     person_id = str(deal['person_id']['value'])
            #     if course_id and person_id and deal['person_id']['value']:
            #         course = state.courses.get(course_id)
            #         state.persons[person_id].courses.append(course)


@expose()
async def create_deal(data, **params):
    pd_post('deals', data)


def format_person(person):
    # view = pdict(name=person['name'], courses=[], email='', phone='', phone_part='', google=person[google_field], id=str(person['id']))
    view = pdict(name=person['name'], courses=set(), email='', phone='', phone_part='', id=str(person['id']))

    for field in ['google', 'telegram']:
        view[field] = person[field]

    if len(person['phone']) and person['phone'][0]['value']:
        view.phone = clean_phone(person['phone'][0]['value'])
        view.phone_part = view.phone[-4:]

    if len(person['email']) and person['email'][0]['value']:
        view.email = person['email'][0]['value'].lower()
    return view


async def reload_data():
    await load_stages()
    await load_person_fields()
    await load_deal_fields()
    await load_persons()
    await load_deals()


def check_key(params, settings):
    pid_input = str(params.get('projectId', ''))
    pid_config = str(settings.get('projectIdKey', ''))
    pids_eq = pid_input == pid_config
    if not pids_eq:
        logger.debug(f'projectId not match: {pid_config}!={pid_input}', st=str(type(pid_config)), inp=str(type(pid_input)))
    return pid_config and pids_eq


# https://bolt.rstat.org/pipedrive/deal/X
# https://bolt.rstat.org/pipedrive/person/X
@expose.handler(timeout=15000)
async def deal(**params):
    if check_key(params, settings):
        await scheduler.spawn(reload_data())
        return {'success': 1}


@expose.handler(timeout=15000)
async def person(**params):
    if check_key(params, settings):
        await scheduler.spawn(reload_data())
        return {'success': 1}


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
