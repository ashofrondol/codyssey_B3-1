"""Mini Redis CLI(REPL) 진입점.

표준 입력에서 한 줄씩 받아 토큰화하고, 해당 명령을 MiniRedis로 보낸 다음
결과를 Redis 스타일 문자열로 출력한다.

진입점은 이 모듈이 아니라 저장소 루트의 main.py 다. 여기에 __main__ 블록을
두면 `python minredis/cli.py` 가 되는 것처럼 보이지만, 상대 import 때문에
실제로는 ImportError 로 끝난다 — 되지 않는 실행 경로를 광고하지 않는다.

사용 예:
    python main.py
    mini-redis> SET user:1 "Alice"
    OK
    mini-redis> GET user:1
    "Alice"
    mini-redis> exit
"""

import re
from typing import Callable, NamedTuple, Optional

from .mini_redis import ERR_NOT_INTEGER, MiniRedis
from .protocol import ResultKind


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
    if kind == ResultKind.OK:
        return 'OK'
    if kind == ResultKind.NIL:
        return '(nil)'
    if kind == ResultKind.INT:
        return f'(integer) {result[1]}'
    if kind == ResultKind.BULK:
        return f'"{result[1]}"'
    if kind == ResultKind.ERROR:
        return f'(error) {result[1]}'
    if kind == ResultKind.ARRAY:
        items = result[1]
        if not items:
            return '(empty array)'
        lines = []
        for i, item in enumerate(items, 1):
            lines.append(f'{i}) "{item}"')
        return '\n'.join(lines)
    if kind == ResultKind.INFO:
        _, used, maxm, evicted = result
        return (f'used_memory:{used}\n'
                f'maxmemory:{maxm}\n'
                f'evicted_keys:{evicted}')
    # 모르는 종류를 빈 문자열로 삼키면 REPL에 빈 줄만 찍히고 아무도 모른다.
    # 새 명령을 추가하면서 여기 분기를 빠뜨리는 것이 정확히 그 경로였다.
    raise ValueError(f'unknown result kind: {kind!r}')


# ---------- 명령 디스패처 ----------

def _wrong_args(cmd):
    return (ResultKind.ERROR, f"ERR wrong number of arguments for '{cmd}' command")


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


class _Command(NamedTuple):
    """명령 테이블의 한 행.

    이름을 분기 조건과 에러 문구에 각각 적으면 둘은 언젠가 어긋난다.
    여기서는 이름을 한 번만 적고 `_wrong_args`가 같은 값을 읽어 쓴다.
    """

    name: str                 # 표시용 이름. 에러 문구에 그대로 들어간다.
    min_args: int             # 허용 최소 인자 수
    max_args: Optional[int]   # 허용 최대 인자 수. None이면 상한 없음.
    handler: Callable         # (redis, args) -> 결과 튜플


def _handle_config(redis, args):
    """CONFIG SET maxmemory <bytes>.

    서브커맨드마다 인자 수가 달라 표의 (min, max) 한 쌍으로는 표현되지
    않는다. 표는 'CONFIG에는 최소 1개'까지만 알고, 그 안쪽은 여기서 본다.
    """
    sub_command = args[0].upper()
    if sub_command != 'SET':
        return (ResultKind.ERROR, f"ERR Unsupported CONFIG subcommand: {args[0]}")
    if len(args) != 3:
        return _wrong_args('CONFIG')
    param = args[1].lower()
    if param != 'maxmemory':
        return (ResultKind.ERROR, f"ERR Unsupported CONFIG parameter: {args[1]}")
    try:
        value = _parse_int(args[2])
    except ValueError:
        return (ResultKind.ERROR, ERR_NOT_INTEGER)
    return redis.cmd_config_set_maxmemory(value)


def _handle_info(redis, args):
    """INFO [memory]. 인자가 없거나 'memory'만 처리한다(다른 섹션은 미구현)."""
    if len(args) == 1 and args[0].lower() != 'memory':
        return (ResultKind.ERROR, f"ERR Unsupported INFO section: {args[0]}")
    return redis.cmd_info_memory()


def _handle_expire(redis, args):
    try:
        seconds = _parse_int(args[1])
    except ValueError:
        return (ResultKind.ERROR, ERR_NOT_INTEGER)
    return redis.cmd_expire(args[0], seconds)


# 지원하는 모든 명령. 새 명령은 이 표에 한 줄을 더하는 것으로 끝난다.
# dispatch()는 이 표를 순회할 뿐이고, 인자 개수 검사(tests/test_cli.py의
# TestCommandTableArity)도 같은 표에서 생성된다 — 표에 추가하면 검사가
# 저절로 따라붙고, 빠뜨리면 조용히 넘어갈 곳이 없다.
#
# KEYS는 명세상 패턴 매칭이 미구현이라 인자를 받지 않는다. 인자를 조용히
# 무시하면 `KEYS *`가 마치 패턴 매칭이 되는 것처럼 보이는 잘못된 신호를 준다.
#
# EXIT/QUIT는 엔진이 아니라 REPL에 보내는 신호라 handler가 redis를 쓰지 않는다.
# 인자 상한을 두지 않는 것은 `exit` 뒤에 무엇이 붙든 종료시키기 위해서다.
COMMANDS = (
    _Command('SET',     2, 2,    lambda redis, args: redis.cmd_set(args[0], args[1])),
    _Command('GET',     1, 1,    lambda redis, args: redis.cmd_get(args[0])),
    _Command('DEL',     1, 1,    lambda redis, args: redis.cmd_del(args[0])),
    _Command('EXISTS',  1, 1,    lambda redis, args: redis.cmd_exists(args[0])),
    _Command('DBSIZE',  0, 0,    lambda redis, args: redis.cmd_dbsize()),
    _Command('KEYS',    0, 0,    lambda redis, args: redis.cmd_keys()),
    _Command('CONFIG',  1, None, _handle_config),
    _Command('INFO',    0, 1,    _handle_info),
    _Command('EXPIRE',  2, 2,    _handle_expire),
    _Command('TTL',     1, 1,    lambda redis, args: redis.cmd_ttl(args[0])),
    _Command('EXIT',    0, None, lambda redis, args: (ResultKind.EXIT,)),
    _Command('QUIT',    0, None, lambda redis, args: (ResultKind.EXIT,)),
)


def lookup(name):
    """대문자 명령 이름으로 표에서 행을 찾는다. 없으면 None.

    명령이 12개뿐이라 선형 탐색으로 충분하다.
    """
    for command in COMMANDS:
        if command.name == name:
            return command
    return None


def dispatch(redis, tokens):
    """토큰 리스트를 받아 적절한 명령을 실행하고 결과 튜플을 돌려준다.

    종료를 원하면 (ResultKind.EXIT,)를 반환한다.
    """
    if not tokens:
        return None
    raw_cmd = tokens[0]
    command = lookup(raw_cmd.upper())
    if command is None:
        return (ResultKind.ERROR, f"ERR unknown command '{raw_cmd}'")

    args = tokens[1:]
    if len(args) < command.min_args:
        return _wrong_args(command.name)
    if command.max_args is not None and len(args) > command.max_args:
        return _wrong_args(command.name)
    return command.handler(redis, args)


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
            if result[0] == ResultKind.EXIT:
                break
            output = format_result(result)
        except Exception as e:  # noqa: BLE001 - CLI 최상위 방어선
            print(f'(error) ERR internal error: {e}')
            continue
        print(output)

