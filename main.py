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

from mini_redis import MiniRedis


# ---------- 토크나이저 ----------

def tokenize(line):
    """공백으로 토큰을 나누되, 큰따옴표("...")로 감싼 부분은 한 토큰으로 묶는다.

    간단한 이스케이프(\\", \\\\, \\n, \\t)를 지원한다.
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
                raise ValueError("unterminated string")
            i += 1  # 닫는 " 건너뛰기
            tokens.append(''.join(buf))
        else:
            # 공백/따옴표가 나올 때까지를 한 토큰으로
            buf = []
            while i < n and not line[i].isspace() and line[i] != '"':
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


def _parse_int(s):
    """정수 파싱. 부호/공백 허용. 실패 시 ValueError."""
    return int(s)


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
        # 단순화: 인자가 있어도 무시(스펙은 패턴 매칭을 구현하지 않음)
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
                return ('error', 'ERR value is not an integer or out of range')
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
            return ('error', 'ERR value is not an integer or out of range')
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

        line = line.strip()
        if not line:
            continue

        try:
            tokens = tokenize(line)
        except ValueError as e:
            print(f'(error) ERR {e}')
            continue

        result = dispatch(redis, tokens)
        if result is None:
            continue
        if result[0] == 'exit':
            break
        print(format_result(result))


if __name__ == '__main__':
    repl()
