import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from itertools import combinations
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).parent / 'warehouse/bd_tables')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'passenger_criteria.md')
    parser.add_argument('--top', type=int, default=20)
    parser.add_argument('--data-output', type=Path, help='Optional full criterion results as JSON')
    args = parser.parse_args()
    if args.top < 1:
        parser.error('--top must be positive')

    def rows(filename):
        with (args.input / filename).open(encoding='utf-8-sig', newline='') as handle:
            yield from csv.DictReader(handle)

    names = defaultdict(set)
    births = defaultdict(set)
    flights = defaultdict(set)
    manifests = defaultdict(set)
    trips = defaultdict(set)
    ticket_flight_keys = set()
    documents = set()

    def name(row):
        return row['PassengerFirstName'], row['PassengerLastName']

    for row in rows('passangers.csv'):
        doc = row['PassengerDocument']
        if not doc:
            continue
        documents.add(doc)
        if all(name(row)):
            names[doc].add(name(row))
        if row['PassengerBirthDate']:
            births[doc].add(row['PassengerBirthDate'])

    for row in rows('tickets.csv'):
        doc = row['PassengerDocument']
        if not doc:
            continue
        documents.add(doc)
        if all(name(row)):
            names[doc].add(name(row))
        if row['FlightDate'] and row['FlightNumber']:
            flight = row['FlightDate'], row['FlightNumber']
            flights[doc].add(flight)
            manifests[flight].add(doc)
            ticket_flight_keys.add(flight)
            if row['FlightTime']:
                try:
                    departure = datetime.fromisoformat(row['FlightDate'] + 'T' + row['FlightTime'])
                    arrival = (datetime.fromisoformat(row['ArrivalDate'] + 'T' + row['ArrivalTime'])
                               if row['ArrivalDate'] and row['ArrivalTime'] else None)
                except ValueError:
                    continue
                trips[doc].add((flight, departure, arrival))

    cards = defaultdict(set)
    for row in rows('loyalty.csv'):
        doc = row['PassengerDocument']
        card = row['CardNumber']
        if doc and card:
            cards[card].add(doc)
    card_partners = defaultdict(set)
    shared_cards = defaultdict(list)
    for card, card_docs in cards.items():
        by_length = defaultdict(set)
        for doc in card_docs:
            by_length[len(''.join(doc.split()))].add(doc)
        for same_length_docs in by_length.values():
            if len(same_length_docs) < 2:
                continue
            for doc in same_length_docs & documents:
                others = same_length_docs - {doc}
                card_partners[doc].update(others)
                shared_cards[doc].append((card, len(others)))

    countries = {}
    ambiguous = set()
    country_labels = set()
    for row in rows('flights.csv'):
        country_labels.update((row['OriginCountry'], row['DestinationCountry']))
        flight = row['FlightDate'], row['FlightNumber']
        if flight not in ticket_flight_keys or flight in ambiguous:
            continue
        route = row['OriginCountry'], row['DestinationCountry']
        if not all(route):
            continue
        if flight in countries and countries[flight] != route:
            ambiguous.add(flight)
            del countries[flight]
        else:
            countries[flight] = route
    shortened_countries = {
        label for label in country_labels if label and (
            len(label) < 4 or any(
                other != label and other.startswith(label) for other in country_labels))
    }

    scores = [dict() for _ in range(8)]
    ages = []
    for doc in documents:
        if len(names[doc]) > 1:
            scores[0][doc] = (len(names[doc]), 'Разных сочетаний имени и фамилии')
        if len(births[doc]) > 1:
            scores[1][doc] = (len(births[doc]), 'Разных дат рождения')
        if card_partners[doc]:
            detail = '; '.join(
                f'карта {card}: ещё {count} документ(ов)'
                for card, count in sorted(shared_cards[doc])[:10]
            )
            scores[2][doc] = (
                len(card_partners[doc]),
                f'Других документов на общих картах: {len(card_partners[doc])}. {detail}',
            )
        months = Counter(date[:7] for date, number in flights[doc])
        busy_months = {month: count for month, count in months.items() if count >= 10}
        if busy_months:
            detail = '; '.join(f'{month}: {count}' for month, count in sorted(busy_months.items()))
            scores[4][doc] = (max(busy_months.values()), 'Рейсов за месяц — ' + detail)

        ordered = sorted(trips[doc], key=lambda trip: (trip[1], trip[0]))
        overlaps = []
        country_jumps = []
        for i, (flight_a, dep_a, arr_a) in enumerate(ordered):
            for flight_b, dep_b, arr_b in ordered[i + 1:]:
                if flight_a == flight_b:
                    continue
                if (arr_a is not None and arr_b is not None and
                        arr_a > dep_a and arr_b > dep_b and dep_b < arr_a):
                    overlaps.append(f'{flight_a[1]} {dep_a:%Y-%m-%d %H:%M}–{arr_a:%Y-%m-%d %H:%M} / '
                                    f'{flight_b[1]} {dep_b:%Y-%m-%d %H:%M}–{arr_b:%Y-%m-%d %H:%M}')
                if (arr_a is not None and arr_a >= dep_a and
                        timedelta(0) <= dep_b - arr_a <= timedelta(hours=1)):
                    prior_route = countries.get(flight_a)
                    next_route = countries.get(flight_b)
                    if (prior_route and next_route and
                            prior_route[1] not in shortened_countries and
                            next_route[0] not in shortened_countries and
                            prior_route[1] != next_route[0]):
                        country_jumps.append(
                            f'{prior_route[1]}: {flight_a[1]} прилёт {arr_a:%Y-%m-%d %H:%M} → '
                            f'{next_route[0]}: {flight_b[1]} вылет {dep_b:%Y-%m-%d %H:%M}')
        if overlaps:
            scores[5][doc] = (len(overlaps), 'Пересекающиеся пары рейсов: ' +
                              '; '.join(overlaps[:10]))
        if country_jumps:
            scores[6][doc] = (len(country_jumps), 'Разные страны в пределах часа: ' +
                              '; '.join(country_jumps[:10]))
        if len(births[doc]) == 1 and flights[doc]:
            try:
                born = date.fromisoformat(next(iter(births[doc])))
                last_flight = date.fromisoformat(max(day for day, _ in flights[doc]))
            except ValueError:
                continue
            age = (last_flight.year - born.year -
                   ((last_flight.month, last_flight.day) < (born.month, born.day)))
            if age >= 0:
                ages.append((born, doc, last_flight, age))
                if age >= 60:
                    scores[7][doc] = (age, f'Возраст на дату последнего билета '
                                           f'{last_flight}: {age} лет')

    pairs = Counter()
    for passengers in manifests.values():
        pairs.update(combinations(sorted(passengers), 2))
    partners = defaultdict(list)
    for (a, b), count in pairs.items():
        if count >= 3:
            partners[a].append((b, count))
            partners[b].append((a, count))
    for doc, people in partners.items():
        if not any(doc in score for index, score in enumerate(scores) if index != 3):
            continue
        ordered = sorted(people, key=lambda item: (-item[1], item[0]))
        detail = '; '.join(f'{other}: {count} рейсов' for other, count in ordered[:10])
        scores[3][doc] = (max(count for _, count in people),
                          f'Спутников с ≥3 общими рейсами: {len(people)}. ' + detail)

    titles = [
        'Один документ — разные имя или фамилия',
        'Один документ — разные даты рождения',
        'Одна карта лояльности связана с паспортами одинаковой длины',
        'Три и более совместных рейса с одним пассажиром',
        'Десять и более рейсов за календарный месяц',
        'Одновременное нахождение на двух разных рейсах',
        'Прилёт и вылет из разных стран в пределах часа',
        'Возраст 60 лет и старше на дату последнего билета',
    ]

    if args.data_output:
        selected = set().union(*scores)
        payload = {
            'criteria': titles,
            'people': {
                doc: {
                    'names': [' '.join(n) for n in sorted(names[doc])],
                    'birth_dates': sorted(births[doc]),
                    'matches': {
                        str(index): {'value': value, 'detail': detail}
                        for index, score in enumerate(scores, 1)
                        if doc in score
                        for value, detail in [score[doc]]
                    },
                }
                for doc in sorted(selected)
            },
        }
        args.data_output.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')

    lines = [
        '# Отбор пассажиров по восьми критериям', '',
        'Пассажир здесь — уникальное исходное значение PassengerDocument. '
        'Это список совпадений с правилами, а не доказательство шпионажа.', '',
        f'Всего документов в пассажирах и билетах: **{len(documents):,}**.',
        f'Хотя бы один критерий: **{len(set().union(*scores)):,}** документов.', '',
        'Исходные CSV не изменяются. Значения сравниваются буквально, без исправления '
        'регистра, пробелов и транслитерации. Отчество в критериях не используется. '
        'Пустые документы, имена, фамилии и даты рождения не считаются противоречиями.', '',
        'Критерий 3: один CardNumber в loyalty.csv связан с двумя или '
        'более разными PassengerDocument одинаковой длины независимо от '
        'ProgramCode. Пробелы при измерении длины не считаются. '
        'Повтор одной и той же пары карты и документа не учитывается. '
        'Это обычная ситуация и сама по себе '
        'не доказывает подозрительное поведение.', '',
        'Рейс для подсчёта — пара FlightDate + FlightNumber. Повторы строк не увеличивают '
        'число рейсов. Билеты не подтверждают фактический перелёт. '
        'Критерий совместных рейсов означает совпадение этой пары полей, '
        'а не доказанную встречу. Прежний критерий 5 (теперь критерий 4) '
        'засчитывается пассажиру только при наличии у него другого критерия.', '',
        'Критерий 6: интервалы двух разных рейсов пересекаются; оба рейса '
        'должны иметь дату и время вылета и прилёта. Если их нет, пара '
        'пропускается как недостаточно данных. Критерий 7: после записанного прилёта '
        'в течение 0–60 минут указан вылет из другой страны; учитываются только '
        'однозначные страны рейсов из flights.csv; названия, встречающиеся как '
        'сокращённое начало другого названия страны, и названия короче '
        'четырёх символов исключены. '
        'Сравниваются часы ровно как '
        'они записаны в CSV: часовых поясов в данных нет, поэтому временные '
        'совпадения и страновой критерий требуют отдельной проверки.', '',
        'Критерий 8: возраст 60+ на дату последнего билета. При нескольких '
        'разных датах рождения одного документа возраст не определяется. '
        'Отдельный топ-20 самых старших отсортирован по дате рождения.', '',
        'Источники: warehouse/bd_tables/passangers.csv, '
        'warehouse/bd_tables/tickets.csv, warehouse/bd_tables/flights.csv '
        'и warehouse/bd_tables/loyalty.csv.', '',
        '| № | Критерий | Количество пассажиров |',
        '|---|---|---:|',
    ]
    for index, (title, score) in enumerate(zip(titles, scores), 1):
        lines.append(f'| {index} | {title} | {len(score)} |')
    lines += ['', 'Один пассажир может входить в несколько критериев.']
    for index, (title, score) in enumerate(zip(titles, scores), 1):
        lines += ['', f'## {index}. {title}', '',
                  f'Всего: **{len(score)}**. Топ-{args.top} по величине показателя '
                  '(при равенстве — по документу).', '',
                  '| Документ | Имя и фамилия: все варианты | Даты рождения | Показатель | Детали |',
                  '|---|---|---|---:|---|']
        for doc, (value, detail) in sorted(score.items(), key=lambda item: (-item[1][0], item[0]))[:args.top]:
            fields = [doc, '; '.join(' '.join(n) for n in sorted(names[doc])),
                      '; '.join(sorted(births[doc])), value, detail]
            lines.append('| ' + ' | '.join(cell(field) for field in fields) + ' |')
        if not score:
            lines += ['', 'Совпадений нет.']
    lines += ['', f'## Топ-{args.top} самых старших пассажиров', '',
              'Сортировка по самой ранней дате рождения. Возраст указан на дату '
              'последнего билета пассажира. Документы с несколькими датами '
              'рождения или без билетов не включены.', '',
              '| Документ | Имя и фамилия | Дата рождения | Последний билет | Возраст на тот день |',
              '|---|---|---|---|---:|']
    for born, doc, last_flight, age in sorted(ages)[:args.top]:
        fields = [doc, '; '.join(' '.join(n) for n in sorted(names[doc])),
                  born, last_flight, age]
        lines.append('| ' + ' | '.join(cell(field) for field in fields) + ' |')
    args.output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for title, score in zip(titles, scores):
        print(f'{title}: {len(score)}')
    print(f'Report: {args.output}')


if __name__ == '__main__':
    main()
