import json
import math
import re
import time
from pathlib import Path

EPSILON = 1e-9
REPEATS = 10
SIZES = (3, 5, 13, 25)


def normalize_label(value):
    if not isinstance(value, str):
        raise ValueError('라벨은 문자열이어야 합니다')
    label = value.strip().lower()
    if label in ('+', 'cross'):
        return 'Cross'
    if label == 'x':
        return 'X'
    raise ValueError('알 수 없는 라벨: {!r}'.format(value))


def validate_matrix(matrix, n, name):
    if not isinstance(matrix, list) or len(matrix) != n:
        raise ValueError('{}: 행 수가 {}이어야 합니다'.format(name, n))
    for i, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != n:
            raise ValueError('{}: {}번째 행의 열 수가 {}이어야 합니다'.format(name, i + 1, n))
        for item in row:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError('{}: 유한한 숫자만 허용됩니다'.format(name))
    return matrix


def mac(pattern, filt):
    total = 0.0
    for i in range(len(pattern)):
        for j in range(len(pattern[i])):
            total += pattern[i][j] * filt[i][j]
    return total


def decide(a, b, first='A', second='B'):
    if abs(a - b) < EPSILON:
        return 'UNDECIDED'
    return first if a > b else second


def measure(pattern, filt, repeats=REPEATS):
    durations = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        mac(pattern, filt)
        durations.append((time.perf_counter_ns() - start) / 1_000_000)
    return sum(durations) / len(durations)


def generated_pattern(n, kind):
    if kind == 'Cross':
        return [[int(i == n // 2 or j == n // 2) for j in range(n)] for i in range(n)]
    return [[int(i == j or i + j == n - 1) for j in range(n)] for i in range(n)]


def performance(filters=None):
    print('\n[성능 분석: 각 크기별 10회 평균, MAC 1회 기준]')
    print('{:<10} {:>16} {:>12}'.format('크기', '평균 시간(ms)', '연산 횟수'))
    print('-' * 42)
    for n in SIZES:
        pattern = generated_pattern(n, 'Cross')
        filt = generated_pattern(n, 'Cross')
        if filters and n in filters:
            filt = filters[n]['Cross']
        print('{:<10} {:>16.6f} {:>12}'.format('{}x{}'.format(n, n), measure(pattern, filt), n * n))


def read_matrix(name):
    print('{} (3줄, 각 줄에 숫자 3개)'.format(name))
    rows = []
    while len(rows) < 3:
        try:
            parts = input('  {}행> '.format(len(rows) + 1)).split()
        except EOFError:
            raise KeyboardInterrupt
        if len(parts) != 3:
            print('입력 형식 오류: 각 줄에 3개의 숫자를 공백으로 구분해 입력하세요.')
            continue
        try:
            row = [float(part) for part in parts]
            if not all(math.isfinite(x) for x in row):
                raise ValueError
        except ValueError:
            print('입력 형식 오류: 유한한 숫자 3개를 입력하세요.')
            continue
        rows.append(row)
    return rows


def manual_mode():
    print('\n[1] 필터 입력')
    a = read_matrix('필터 A')
    b = read_matrix('필터 B')
    print('필터 A, B 저장 완료 (각 3x3)')
    print('\n[2] 패턴 입력')
    pattern = read_matrix('패턴')
    score_a = mac(pattern, a)
    score_b = mac(pattern, b)
    print('\n[3] MAC 결과')
    print('A 점수: {:.16g}'.format(score_a))
    print('B 점수: {:.16g}'.format(score_b))
    print('연산 시간(두 필터 각각 10회 평균 합계): {:.6f} ms'.format(measure(pattern, a) + measure(pattern, b)))
    result = decide(score_a, score_b)
    print('판정: {}'.format('판정 불가 (UNDECIDED)' if result == 'UNDECIDED' else result))
    performance()


def parse_filters(raw):
    if not isinstance(raw, dict):
        raise ValueError('filters는 객체여야 합니다')
    valid, errors = {}, {}
    for n in (5, 13, 25):
        key = 'size_{}'.format(n)
        try:
            group = raw[key]
            if not isinstance(group, dict):
                raise ValueError('필터 그룹은 객체여야 합니다')
            normalized = {}
            for label, matrix in group.items():
                canonical = normalize_label(label)
                if canonical in normalized:
                    raise ValueError('중복 필터 라벨: {}'.format(canonical))
                normalized[canonical] = validate_matrix(matrix, n, key + '/' + label)
            if set(normalized) != {'Cross', 'X'}:
                raise ValueError('Cross와 X 필터가 모두 필요합니다')
            valid[n] = normalized
            print('✓ {} 필터 로드 완료 (Cross, X)'.format(key))
        except (KeyError, ValueError, TypeError) as exc:
            errors[n] = str(exc)
            print('✗ {} 필터 오류: {}'.format(key, exc))
    return valid, errors


def load_patterns(raw):
    if isinstance(raw, dict):
        return raw.items()
    raise ValueError('patterns는 키-케이스 객체여야 합니다')


def json_mode(path):
    print('\n[1] 필터 로드')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print('data.json 읽기 실패: {}'.format(exc))
        return
    if not isinstance(data, dict):
        print('스키마 오류: JSON 최상위는 객체여야 합니다')
        return
    filters, filter_errors = parse_filters(data.get('filters'))
    print('\n[2] 패턴 분석')
    try:
        cases = load_patterns(data.get('patterns'))
    except ValueError as exc:
        print('스키마 오류: {}'.format(exc))
        return
    total = passed = 0
    failures = []
    for key, case in cases:
        total += 1
        print('\n--- {} ---'.format(key))
        try:
            match = re.fullmatch(r'size_(\d+)_(\d+)', key)
            if not match:
                raise ValueError('패턴 키 형식 오류 (size_N_idx 필요)')
            n = int(match.group(1))
            if n not in (5, 13, 25):
                raise ValueError('지원하지 않는 크기: {}'.format(n))
            if n in filter_errors:
                raise ValueError('필터 스키마 오류: {}'.format(filter_errors[n]))
            if not isinstance(case, dict):
                raise ValueError('케이스는 객체여야 합니다')
            pattern = validate_matrix(case.get('input'), n, key + '/input')
            expected = normalize_label(case.get('expected'))
            cross = mac(pattern, filters[n]['Cross'])
            x = mac(pattern, filters[n]['X'])
            predicted = decide(cross, x, 'Cross', 'X')
            print('Cross 점수: {:.16g}'.format(cross))
            print('X 점수: {:.16g}'.format(x))
            if predicted == expected:
                passed += 1
                print('판정: {} | expected: {} | PASS'.format(predicted, expected))
            else:
                reason = 'epsilon 동점 정책으로 UNDECIDED' if predicted == 'UNDECIDED' else '예측과 expected 불일치 (데이터 또는 판정 로직 확인)'
                failures.append((key, reason))
                print('판정: {} | expected: {} | FAIL ({})'.format(predicted, expected, reason))
        except (ValueError, TypeError, KeyError) as exc:
            reason = '데이터/스키마 오류: {}'.format(exc)
            failures.append((key, reason))
            print('FAIL ({})'.format(reason))
    performance(filters)
    print('\n[4] 결과 요약')
    print('총 테스트: {}개 | 통과: {}개 | 실패: {}개'.format(total, passed, len(failures)))
    if failures:
        print('실패 케이스:')
        for key, reason in failures:
            print('- {}: {}'.format(key, reason))
    else:
        print('실패 케이스 없음')


def main():
    print('=== Mini NPU Simulator ===')
    print('1. 사용자 입력 (3x3)\n2. data.json 분석')
    while True:
        try:
            choice = input('선택: ').strip()
        except EOFError:
            return
        if choice in ('1', '2'):
            break
        print('1 또는 2를 입력하세요.')
    try:
        if choice == '1':
            manual_mode()
        else:
            json_mode(Path(__file__).resolve().parent / 'data.json')
    except KeyboardInterrupt:
        print('\n입력이 종료되었습니다.')


if __name__ == '__main__':
    main()
