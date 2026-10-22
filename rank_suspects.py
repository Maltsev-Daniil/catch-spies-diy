import argparse
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

WEIGHTS = {
    1: 8,  # Different names for the same document
    2: 7,  # Different birth dates for the same document
    3: 1,  # Same card with distinct passports of equal length
    4: 2,  # Repeated shared flights, only alongside another criterion
    5: 1,  # High monthly flight count
    6: 3,  # Flights overlap in recorded time
    7: 7,  # Country changes within an hour in recorded time
    8: 1,  # Age 60+ alone is weak evidence
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).parent / 'warehouse/bd_tables')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'suspect_ranking.md')
    parser.add_argument('--top', type=int, default=20)
    args = parser.parse_args()
    if args.top < 1:
        parser.error('--top must be positive')

    with TemporaryDirectory() as directory:
        temp = Path(directory)
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name('passenger_criteria.py')),
             '--input', str(args.input), '--output', str(temp / 'criteria.md'),
             '--data-output', str(temp / 'criteria.json')],
            check=True, capture_output=True, text=True,
        )
        data = json.loads((temp / 'criteria.json').read_text(encoding='utf-8'))

    criteria = data['criteria']
    if len(criteria) != len(WEIGHTS):
        raise RuntimeError('Update WEIGHTS to match the criteria in passenger_criteria.py')

    ranked = []
    for doc, person in data['people'].items():
        matches = {int(number): evidence for number, evidence in person['matches'].items()}
        if len(matches) < 2:
            continue
        points = sum(WEIGHTS[number] for number in matches)
        ranked.append((points, len(matches), doc, person, matches))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))

    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')

    lines = [
        '# Топ пассажиров по пересечению критериев', '',
        'Один человек в этом расчёте — один PassengerDocument. В рейтинг входят '
        'только документы с двумя и более сработавшими критериями. Баллы задают '
        'порядок ручной проверки, а не вероятность того, что человек шпион.', '',
        f'Пассажиров с ≥2 критериями: **{len(ranked)}**.', '',
        '| № | Критерий | Баллы |', '|---|---|---:|',
    ]
    for number, title in enumerate(criteria, 1):
        lines.append(f'| {number} | {cell(title)} | {WEIGHTS[number]} |')
    lines += ['', 'Каждый критерий добавляет баллы один раз, даже если совпадение '
              'повторилось. При равных баллах выше человек с большим числом '
              'критериев, затем сортировка по документу. Временные признаки '
              'сравнивают записанные часы без часовых поясов; возможны ошибки '
              'в исходных данных.', '',
              f'## Топ-{args.top}', '',
              '| Место | Документ | Имя и фамилия | Баллы | Критериев | Сработали № |',
              '|---:|---|---|---:|---:|---|']
    for place, (points, count, doc, person, matches) in enumerate(ranked[:args.top], 1):
        fields = [place, doc, '; '.join(person['names']), points, count,
                  ', '.join(str(n) for n in sorted(matches))]
        lines.append('| ' + ' | '.join(cell(field) for field in fields) + ' |')

    lines += ['', '## Почему они попали в топ', '']
    for place, (points, count, doc, person, matches) in enumerate(ranked[:args.top], 1):
        lines.append(f'### {place}. {cell("; ".join(person["names"]))} — '
                     f'{cell(doc)}, {points} баллов')
        lines.append('')
        for number in sorted(matches):
            evidence = matches[number]
            lines.append(f'- **№ {number}, +{WEIGHTS[number]}:** '
                         f'{cell(criteria[number - 1])}. {cell(evidence["detail"])}')
        lines.append('')
    if not ranked:
        lines += ['Совпадений по двум критериям нет.', '']

    args.output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Passengers with at least two criteria: {len(ranked)}')
    print(f'Report: {args.output}')


if __name__ == '__main__':
    main()
