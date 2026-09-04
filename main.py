"""Mini Redis CLI(REPL) 진입점.

표준 입력에서 한 줄씩 받아 토큰화하고, 해당 명령을 MiniRedis로 보낸 다음
결과를 Redis 스타일 문자열로 출력한다.

사용 예:
    python main.py
    mini-redis> SET user:1 "Alice"
    OK
    mini-redis> GET user:1
    "Alice"
    mini-redis> exit
"""

import re

from mini_redis import ERR_NOT_INTEGER, MiniRedis


_UNBALANCED_QUOTES = 'Protocol error: unbalanced quotes in request'


# ---------- 토크나이저 ----------

def tokenize(line):
    """공백으로 토큰을 나누되, 큰따옴표("...")로 감싼 부분은 한 토큰으로 묶는다.

    간단한 이스케이프(\\", \\\\, \\n, \\t)를 지원한다.
    따옴표가 짝이 맞지 않으면(닫히지 않았거나 토큰 중간에 나타나면)
    ValueError를 던진다. 호출자가 표준 에러 문자열로 변환한다.
    """
    tokens = []
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            # 큰따옴표로 감싼 문자열
            i += 1
            buf = []
            while i < n and line[i] != '"':
                if line[i] == '\\' and i + 1 < n:
                    nxt = line[i + 1]
                    if nxt == 'n':
                        buf.append('\n')
                    elif nxt == 't':
                        buf.append('\t')
                    elif nxt == '"':
                        buf.append('"')
                    elif nxt == '\\':
                        buf.append('\\')
                    else:
                        buf.append(nxt)
                    i += 2
                else:
                    buf.append(line[i])
                    i += 1
            if i >= n:
                raise ValueError(_UNBALANCED_QUOTES)
            i += 1  # 닫는 " 건너뛰기
            # 닫는 따옴표 뒤에는 공백이나 줄 끝만 올 수 있다. 이 검사가 없으면
            # SET k "ab"cd 가 토큰 4개로 쪼개져 진짜 원인과 무관한
            # '인자 개수 오류'가 보고된다(아래 else 분기와의 비대칭).
            if i < n and not line[i].isspace():
                raise ValueError(_UNBALANCED_QUOTES)
            tokens.append(''.join(buf))
        else:
            # 공백이 나올 때까지를 한 토큰으로.
            # 토큰 중간에 나타난 따옴표는 인용 부호 불균형으로 본다.
            # (그렇지 않으면 SET k ab"cd" 가 토큰 3개로 쪼개져
            #  진짜 원인과 무관한 '인자 개수 오류'가 보고된다.)
            buf = []
            while i < n and not line[i].isspace():
                if line[i] == '"':
                    raise ValueError(_UNBALANCED_QUOTES)
                buf.append(line[i])
                i += 1
            tokens.append(''.join(buf))
    return tokens


# ---------- 결과 포매터 ----------

def format_result(result):
    """MiniRedis가 돌려준 튜플을 사람이 읽을 문자열로 변환한다."""
    kind = result[0]
    if kind == 'ok':
        return 'OK'
    if kind == 'nil':
        return '(nil)'
    if kind == 'int':
        return f'(integer) {result[1]}'
    if kind == 'bulk':
        return f'"{result[1]}"'
    if kind == 'error':
        return f'(error) {result[1]}'
    if kind == 'array':
        items = result[1]
        if not items:
            return '(empty array)'
        lines = []
        for i, item in enumerate(items, 1):
            lines.append(f'{i}) "{item}"')
        return '\n'.join(lines)
    if kind == 'info':
        _, used, maxm, evicted = result
        return (f'used_memory:{used}\n'
                f'maxmemory:{maxm}\n'
                f'evicted_keys:{evicted}')
    return ''


# ---------- 명령 디스패처 ----------

def _wrong_args(cmd):
    return ('error', f"ERR wrong number of arguments for '{cmd}' command")


# `$`가 아니라 `\Z`를 쓴다. 파이썬에서 `$`는 말미 개행 앞에서도 매치하므로
# 따옴표 안 이스케이프로 만들어진 "1\n" 같은 토큰이 새어나간다.
# `\d`는 유니코드 숫자(아랍-인도 숫자 등)까지 매치하므로 `[0-9]`를 쓴다.
_INT_RE = re.compile(r'^[+-]?[0-9]+\Z')
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1


def _parse_int(s):
    """Redis 호환 정수 파싱. ASCII 부호와 ASCII 숫자만 허용한다.

    int()를 그대로 쓰면 언더스코어 리터럴(1_000), 앞뒤 공백(" 12 "),
    유니코드 Nd 숫자(١٢)가 통과한다. 또 범위 검사가 없으면 EXPIRE의
    float 연산에서 OverflowError가 나 REPL 프로세스가 통째로 죽는다.

    실패 시 ValueError를 던지며, 호출부가 표준 에러 문자열로 변환한다.
    음수 허용은 필수다 — EXPIRE는 seconds <= 0을 '즉시 만료'라는
    명세 동작으로 사용한다.
    """
    if not _INT_RE.match(s):
        raise ValueError('not an integer')
    v = int(s)
    if not (_INT64_MIN <= v <= _INT64_MAX):
        raise ValueError('out of range')
    return v


def dispatch(redis, tokens):
    """토큰 리스트를 받아 적절한 명령을 실행하고 결과 튜플을 돌려준다.

    종료를 원하면 ('exit',)를 반환한다.
    """
    if not tokens:
        return None
    raw_cmd = tokens[0]
    cmd = raw_cmd.upper()
    args = tokens[1:]

    if cmd in ('EXIT', 'QUIT'):
        return ('exit',)

    if cmd == 'SET':
        if len(args) != 2:
            return _wrong_args('SET')
        return redis.cmd_set(args[0], args[1])

    if cmd == 'GET':
        if len(args) != 1:
            return _wrong_args('GET')
        return redis.cmd_get(args[0])

    if cmd == 'DEL':
        if len(args) != 1:
            return _wrong_args('DEL')
        return redis.cmd_del(args[0])

    if cmd == 'EXISTS':
        if len(args) != 1:
            return _wrong_args('EXISTS')
        return redis.cmd_exists(args[0])

    if cmd == 'DBSIZE':
        if len(args) != 0:
            return _wrong_args('DBSIZE')
        return redis.cmd_dbsize()

    if cmd == 'KEYS':
        # 명세상 패턴 매칭은 미구현이므로 인자를 받지 않는 명령이다.
        # DBSIZE와 동일하게 개수를 엄격히 검사한다. 인자를 조용히 무시하면
        # `KEYS *`가 마치 패턴 매칭이 되는 것처럼 보이는 잘못된 신호를 준다.
        if len(args) != 0:
            return _wrong_args('KEYS')
        return redis.cmd_keys()

    if cmd == 'CONFIG':
        if len(args) < 1:
            return _wrong_args('CONFIG')
        sub = args[0].upper()
        if sub == 'SET':
            if len(args) != 3:
                return _wrong_args('CONFIG')
            param = args[1].lower()
            if param != 'maxmemory':
                return ('error', f"ERR Unsupported CONFIG parameter: {args[1]}")
            try:
                v = _parse_int(args[2])
            except ValueError:
                return ('error', ERR_NOT_INTEGER)
            return redis.cmd_config_set_maxmemory(v)
        return ('error', f"ERR Unsupported CONFIG subcommand: {args[0]}")

    if cmd == 'INFO':
        # 인자가 없거나 'memory'만 처리한다. (다른 섹션은 미구현)
        if len(args) > 1:
            return _wrong_args('INFO')
        if len(args) == 1 and args[0].lower() != 'memory':
            return ('error', f"ERR Unsupported INFO section: {args[0]}")
        return redis.cmd_info_memory()

    if cmd == 'EXPIRE':
        if len(args) != 2:
            return _wrong_args('EXPIRE')
        try:
            seconds = _parse_int(args[1])
        except ValueError:
            return ('error', ERR_NOT_INTEGER)
        return redis.cmd_expire(args[0], seconds)

    if cmd == 'TTL':
        if len(args) != 1:
            return _wrong_args('TTL')
        return redis.cmd_ttl(args[0])

    return ('error', f"ERR unknown command '{raw_cmd}'")


# ---------- REPL ----------

def repl(redis=None, prompt='mini-redis> '):
    """대화형 루프. Ctrl+D / Ctrl+C / exit / quit 으로 종료."""
    if redis is None:
        redis = MiniRedis()

    while True:
        try:
            line = input(prompt)
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            # Ctrl+C는 그 한 줄만 무시하고 계속 받는다.
            print()
            continue
        except UnicodeDecodeError:
            # 입력 스트림이 선언된 인코딩으로 디코딩되지 않는다(예: UTF-8 콘솔에
            # UTF-16 붙여넣기). 디코더가 같은 바이트에서 계속 걸려 무한 루프가
            # 되므로 한 줄 무시가 아니라 세션을 정리하며 끝낸다.
            print('(error) ERR Protocol error: invalid input encoding')
            break

        line = line.strip()
        if not line:
            continue

        try:
            tokens = tokenize(line)
        except ValueError as e:
            print(f'(error) ERR {e}')
            continue

        # 최상위 가드: 어떤 내부 예외도 REPL 전체를 죽여 인메모리 데이터를
        # 날리지 못하게 한다. print는 try 밖에 둔다 — 출력 중 BrokenPipe 같은
        # 오류를 '내부 오류'로 오인해 삼키지 않기 위해서다.
        try:
            result = dispatch(redis, tokens)
            if result is None:
                continue
            if result[0] == 'exit':
                break
            output = format_result(result)
        except Exception as e:  # noqa: BLE001 - CLI 최상위 방어선
            print(f'(error) ERR internal error: {e}')
            continue
        print(output)


if __name__ == '__main__':
    repl()
