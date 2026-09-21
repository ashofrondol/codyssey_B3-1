"""CLI 계층(토크나이저 / 디스패처 / 포매터 / REPL) 테스트."""

import contextlib
import io
import unittest

from tests.helpers import ROOT, FakeClock

from minredis import cli
from minredis.cli import (COMMANDS, _parse_int, dispatch, format_result,
                          tokenize)
from minredis.mini_redis import MiniRedis
from minredis.protocol import ResultKind


class TestTokenize(unittest.TestCase):

    def test_plain_tokens(self):
        self.assertEqual(tokenize('SET user:1 Alice'), ['SET', 'user:1', 'Alice'])
        self.assertEqual(tokenize('   GET   k   '), ['GET', 'k'])
        self.assertEqual(tokenize(''), [])

    def test_quoted_value_with_spaces(self):
        self.assertEqual(tokenize('SET k "a b c"'), ['SET', 'k', 'a b c'])
        self.assertEqual(tokenize('SET k ""'), ['SET', 'k', ''])

    def test_escapes(self):
        self.assertEqual(tokenize(r'SET k "a\nb"'), ['SET', 'k', 'a\nb'])
        self.assertEqual(tokenize(r'SET k "a\tb"'), ['SET', 'k', 'a\tb'])
        self.assertEqual(tokenize(r'SET k "a\"b"'), ['SET', 'k', 'a"b'])
        self.assertEqual(tokenize(r'SET k "a\\b"'), ['SET', 'k', 'a\\b'])

    def test_unterminated_quote_raises(self):
        with self.assertRaises(ValueError) as ctx:
            tokenize('SET k "abc')
        self.assertIn('unbalanced quotes', str(ctx.exception))

    def test_quote_inside_token_raises_same_error(self):
        """토큰 중간의 따옴표도 '인자 개수 오류'가 아니라 불균형으로 보고한다."""
        for line in ('SET k a"b', 'SET k ab"cd"ef'):
            with self.assertRaises(ValueError) as ctx:
                tokenize(line)
            self.assertEqual(str(ctx.exception), cli._UNBALANCED_QUOTES)

    def test_closing_quote_must_be_followed_by_space(self):
        """닫는 따옴표 뒤에 바로 문자가 오는 경우도 같은 에러여야 한다(비대칭 방지)."""
        for line in ('SET k "ab"cd', 'SET "k"x v'):
            with self.assertRaises(ValueError) as ctx:
                tokenize(line)
            self.assertEqual(str(ctx.exception), cli._UNBALANCED_QUOTES)
        # 정상 케이스는 영향 없음
        self.assertEqual(tokenize('SET k "a b" '), ['SET', 'k', 'a b'])
        self.assertEqual(tokenize('SET "k" "v"'), ['SET', 'k', 'v'])

    def test_unbalanced_quotes_message_literal(self):
        """에러 문구가 실제 Redis 프로토콜 문구와 일치해야 한다."""
        self.assertEqual(cli._UNBALANCED_QUOTES,
                         'Protocol error: unbalanced quotes in request')


class TestParseInt(unittest.TestCase):

    def test_accepts_plain_and_signed(self):
        self.assertEqual(_parse_int('0'), 0)
        self.assertEqual(_parse_int('30'), 30)
        self.assertEqual(_parse_int('+5'), 5)
        self.assertEqual(_parse_int('-1'), -1)

    def test_rejects_loose_forms(self):
        for bad in ('1_000', ' 12 ', '0x10', '3.0', '', 'abc', '١٢', '1\n', '12abc'):
            with self.assertRaises(ValueError, msg=bad):
                _parse_int(bad)

    def test_int64_bounds(self):
        self.assertEqual(_parse_int('9223372036854775807'), (1 << 63) - 1)
        self.assertEqual(_parse_int('-9223372036854775808'), -(1 << 63))
        with self.assertRaises(ValueError):
            _parse_int('9223372036854775808')
        with self.assertRaises(ValueError):
            _parse_int('1' + '0' * 400)


class TestFormatResult(unittest.TestCase):

    def test_all_kinds(self):
        self.assertEqual(format_result(('ok',)), 'OK')
        self.assertEqual(format_result(('nil',)), '(nil)')
        self.assertEqual(format_result(('int', 5)), '(integer) 5')
        self.assertEqual(format_result(('int', -2)), '(integer) -2')
        self.assertEqual(format_result(('bulk', 'Alice')), '"Alice"')
        self.assertEqual(format_result(('error', 'ERR boom')), '(error) ERR boom')
        self.assertEqual(format_result(('array', [])), '(empty array)')
        self.assertEqual(format_result(('array', ['a', 'b'])), '1) "a"\n2) "b"')
        self.assertEqual(format_result(('info', 22, 30, 1)),
                         'used_memory:22\nmaxmemory:30\nevicted_keys:1')

    def test_unknown_kind_raises_instead_of_printing_blank_line(self):
        """새 명령을 추가하며 여기 분기를 빠뜨리면 빈 줄이 아니라 예외여야 한다.

        예전에는 마지막 줄이 return '' 이라, 포매터에 케이스를 빠뜨려도
        테스트 전부가 통과하고 REPL에는 빈 줄만 찍혔다.
        """
        with self.assertRaises(ValueError) as ctx:
            format_result(('newkind', 1))
        self.assertIn('newkind', str(ctx.exception))

    def test_every_result_kind_has_a_format(self):
        """프로토콜에 선언된 종류는 전부 포매터가 알아야 한다.

        EXIT는 REPL이 가로채므로 포매터에 도달하지 않는다.
        """
        samples = (
            (ResultKind.OK,), (ResultKind.NIL,), (ResultKind.INT, 1),
            (ResultKind.BULK, 'v'), (ResultKind.ARRAY, ['a']),
            (ResultKind.INFO, 0, 0, 0), (ResultKind.ERROR, 'ERR x'),
        )
        formatted = [s[0] for s in samples]
        for kind in ResultKind:
            if kind == ResultKind.EXIT:
                continue
            self.assertIn(kind, formatted, f'{kind} 샘플이 빠졌다')
        for sample in samples:
            with self.subTest(kind=sample[0]):
                self.assertIsInstance(format_result(sample), str)


class TestDispatch(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.r = MiniRedis(now_fn=self.clock)

    def run_line(self, line):
        return dispatch(self.r, tokenize(line))

    def test_case_insensitive_commands(self):
        self.assertEqual(self.run_line('set k v'), ('ok',))
        self.assertEqual(self.run_line('GeT k'), ('bulk', 'v'))
        self.assertEqual(self.run_line('config set MAXMEMORY 100'), ('ok',))
        self.assertEqual(self.run_line('info MEMORY')[0], 'info')
        self.assertEqual(self.run_line('EXIT'), ('exit',))
        self.assertEqual(self.run_line('quit'), ('exit',))

    def test_unknown_command_preserves_input_case(self):
        self.assertEqual(self.run_line('HELLO'),
                         ('error', "ERR unknown command 'HELLO'"))
        self.assertEqual(self.run_line('hello'),
                         ('error', "ERR unknown command 'hello'"))

    def test_config_subcommand_arity(self):
        """표의 (min, max) 한 쌍으로 표현되지 않는 CONFIG 안쪽 인자 수."""
        self.assertEqual(
            self.run_line('CONFIG SET maxmemory'),
            ('error', "ERR wrong number of arguments for 'CONFIG' command"))

    def test_keys_takes_no_arguments(self):
        self.run_line('SET a 1')
        self.assertEqual(self.run_line('KEYS'), ('array', ['a']))
        self.assertEqual(self.run_line('KEYS *')[0], 'error')

    def test_integer_parse_errors(self):
        msg = 'ERR value is not an integer or out of range'
        self.run_line('SET k v')
        self.assertEqual(self.run_line('CONFIG SET maxmemory abc'), ('error', msg))
        self.assertEqual(self.run_line('CONFIG SET maxmemory 3.5'), ('error', msg))
        self.assertEqual(self.run_line('EXPIRE k abc'), ('error', msg))

    def test_huge_integer_is_error_not_crash(self):
        """거대 정수가 OverflowError로 프로세스를 죽이면 안 된다."""
        self.run_line('SET k v')
        huge = '1' + '0' * 400
        self.assertEqual(self.run_line(f'EXPIRE k {huge}')[0], 'error')
        self.assertEqual(self.run_line(f'CONFIG SET maxmemory {huge}')[0], 'error')
        # 상태가 온전한지 확인
        self.assertEqual(self.run_line('GET k'), ('bulk', 'v'))

    def test_int64_max_expire_does_not_crash(self):
        self.run_line('SET k v')
        self.assertEqual(self.run_line('EXPIRE k 9223372036854775807'), ('int', 1))
        self.assertEqual(self.run_line('TTL k')[0], 'int')

    def test_negative_maxmemory_is_error(self):
        self.assertEqual(self.run_line('CONFIG SET maxmemory -1')[0], 'error')

    def test_unsupported_config_and_info(self):
        self.assertEqual(self.run_line('CONFIG GET maxmemory')[0], 'error')
        self.assertEqual(self.run_line('CONFIG SET foo 1')[0], 'error')
        self.assertEqual(self.run_line('INFO cpu')[0], 'error')

    def test_oom_message(self):
        self.run_line('CONFIG SET maxmemory 5')
        result = self.run_line('SET key averylongvalue')
        self.assertEqual(
            result,
            ('error', "OOM command not allowed when used_memory > 'maxmemory'"))

    def test_empty_line_returns_none(self):
        self.assertIsNone(dispatch(self.r, []))

    def test_spec_example_end_to_end(self):
        """명세 실행 예시를 CLI 계층까지 통과시켜 출력 문자열로 고정한다."""
        lines = [
            'CONFIG SET maxmemory 30',
            'SET user:1 "Alice"',
            'SET user:2 "Bob"',
            'SET user:3 "Charlie"',
            'GET user:1',
            'INFO memory',
        ]
        outputs = [format_result(self.run_line(line)) for line in lines]
        self.assertEqual(outputs[:4], ['OK', 'OK', 'OK', 'OK'])
        self.assertEqual(outputs[4], '(nil)')
        self.assertEqual(outputs[5],
                         'used_memory:22\nmaxmemory:30\nevicted_keys:1')
        self.assertEqual(format_result(self.run_line('EXPIRE user:2 3')),
                         '(integer) 1')
        self.assertEqual(format_result(self.run_line('TTL user:2')),
                         '(integer) 3')   # 시계 고정 시 경과 0초 -> 3


def _line_with_args(name, count):
    """명령 이름 + 인자 count개로 이루어진 입력 한 줄."""
    return ' '.join([name] + [f'a{i}' for i in range(count)])


class TestCommandTableArity(unittest.TestCase):
    """인자 개수 에러를 명령 테이블에서 생성해 검사한다.

    예전에는 케이스 13개를 손으로 적어 뒀다. 명령을 추가하면서 줄 추가를
    빠뜨려도 105개 테스트가 전부 통과했다 — 검사가 표를 따라오지 않았기
    때문이다. 이제 표에 행을 더하면 검사가 저절로 붙는다.
    """

    def setUp(self):
        self.r = MiniRedis(now_fn=FakeClock())

    def test_table_covers_every_documented_command(self):
        names = [command.name for command in COMMANDS]
        for expected in ('SET', 'GET', 'DEL', 'EXISTS', 'DBSIZE', 'KEYS',
                         'CONFIG', 'INFO', 'EXPIRE', 'TTL', 'EXIT', 'QUIT'):
            self.assertIn(expected, names)
        self.assertEqual(len(names), len(COMMANDS), '중복된 명령 이름이 있다')

    def test_arity_violations_are_reported_for_every_command(self):
        checked = 0
        for command in COMMANDS:
            lines = []
            if command.min_args > 0:
                lines.append(_line_with_args(command.name, command.min_args - 1))
            if command.max_args is not None:
                lines.append(_line_with_args(command.name, command.max_args + 1))
            for line in lines:
                checked += 1
                with self.subTest(line=line):
                    self.assertEqual(
                        dispatch(self.r, tokenize(line)),
                        ('error', 'ERR wrong number of arguments for '
                                  f"'{command.name}' command"))
        # 표가 전부 (0, None)이 되어 아무것도 검사하지 않는 상태를 막는다.
        self.assertGreaterEqual(checked, 12)

    def test_arity_bounds_are_consistent(self):
        for command in COMMANDS:
            with self.subTest(command=command.name):
                self.assertGreaterEqual(command.min_args, 0)
                if command.max_args is not None:
                    self.assertGreaterEqual(command.max_args, command.min_args)
                self.assertEqual(command.name, command.name.upper())


class _BoomRedis(MiniRedis):
    """cmd_get이 항상 터지는 엔진 — REPL 최상위 가드 검증용."""

    def cmd_get(self, key):
        raise RuntimeError('boom')


class TestReplGuard(unittest.TestCase):
    """REPL이 내부 예외/잘못된 입력에 죽지 않는지 확인한다."""

    def _run_repl(self, lines, redis):
        script = iter(lines)

        def fake_input(prompt=''):
            try:
                return next(script)
            except StopIteration:
                raise EOFError

        buf = io.StringIO()
        cli.input = fake_input           # 모듈 전역이 builtins보다 먼저 조회된다
        try:
            with contextlib.redirect_stdout(buf):
                cli.repl(redis=redis)
        finally:
            del cli.input
        return buf.getvalue()

    def test_internal_exception_does_not_kill_repl(self):
        out = self._run_repl(['GET k', 'DBSIZE', 'exit'],
                             _BoomRedis(now_fn=FakeClock()))
        self.assertIn('(error) ERR internal error: boom', out)
        self.assertIn('(integer) 0', out)   # 이후 명령이 계속 처리된다

    def test_unbalanced_quotes_does_not_kill_repl(self):
        out = self._run_repl(['SET k "abc', 'DBSIZE', 'exit'],
                             MiniRedis(now_fn=FakeClock()))
        self.assertIn('unbalanced quotes', out)
        self.assertIn('(integer) 0', out)

    def test_huge_expire_does_not_kill_repl(self):
        out = self._run_repl(['SET k v', 'EXPIRE k 1' + '0' * 400,
                              'GET k', 'exit'],
                             MiniRedis(now_fn=FakeClock()))
        self.assertIn('(error) ERR value is not an integer or out of range', out)
        self.assertIn('"v"', out)

    def test_blank_lines_are_skipped(self):
        out = self._run_repl(['', '   ', 'DBSIZE', 'exit'],
                             MiniRedis(now_fn=FakeClock()))
        self.assertEqual(out.strip(), '(integer) 0')

    def test_prompt_string_is_exactly_mini_redis(self):
        """명세가 프롬프트 문자열을 고정하고 있다."""
        import inspect
        sig = inspect.signature(cli.repl)
        self.assertEqual(sig.parameters['prompt'].default, 'mini-redis> ')

        seen = []

        def capture_input(prompt=''):
            seen.append(prompt)
            raise EOFError

        cli.input = capture_input
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cli.repl(redis=MiniRedis(now_fn=FakeClock()))
        finally:
            del cli.input
        self.assertEqual(seen, ['mini-redis> '])

    def test_error_line_does_not_terminate_loop(self):
        """에러 뒤에도 루프가 계속되어야 한다(continue를 break로 바꾸면 실패)."""
        out = self._run_repl(['HELLO', 'SET a 1', 'GET a', 'exit'],
                             MiniRedis(now_fn=FakeClock()))
        self.assertIn("unknown command 'HELLO'", out)
        self.assertIn('OK', out)
        self.assertIn('"1"', out)

    def test_quote_error_line_does_not_terminate_loop(self):
        out = self._run_repl(['SET k "abc', 'SET a 1', 'GET a', 'exit'],
                             MiniRedis(now_fn=FakeClock()))
        self.assertIn('unbalanced quotes', out)
        self.assertIn('"1"', out)


class TestConstraints(unittest.TestCase):
    """과제 제약(dict/set/collections 금지, Python 3.8 호환)을 저장소가 스스로 검사한다."""

    BANNED = ('dict', 'set', 'frozenset', 'collections',
              'defaultdict', 'OrderedDict', 'Counter', 'deque')

    # 3.9+ 내장 제네릭 표기(list[str] 등). dict/set/frozenset은 이미 BANNED라
    # 이름 단계에서 걸리므로 여기서는 나머지만 본다. typing 주석을 쓰기
    # 시작한 이상, 다음 사람이 list[str]을 적는 것이 가장 그럴듯한 위반이다.
    BUILTIN_GENERICS = ('list', 'tuple', 'type')

    def test_no_banned_builtins_anywhere(self):
        import ast
        import os

        # 저장소 루트 전체를 훑는다. 패키지 안쪽만 보면 루트 shim과 테스트가
        # 검사 밖으로 빠지고, 새로 생긴 디렉터리는 저절로 검사 범위에 들어온다.
        violations = []
        scanned = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames
                           if d != '__pycache__' and not d.startswith('.')]
            for fn in filenames:
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(dirpath, fn)
                scanned.append(os.path.relpath(path, ROOT))
                with io.open(path, encoding='utf-8') as fh:
                    tree = ast.parse(fh.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id in self.BANNED:
                        violations.append(f'{fn}:{node.lineno}: 금지 이름 {node.id}')
                    elif isinstance(node, (ast.Dict, ast.DictComp)):
                        violations.append(f'{fn}:{node.lineno}: dict 리터럴')
                    elif isinstance(node, (ast.Set, ast.SetComp)):
                        violations.append(f'{fn}:{node.lineno}: set 리터럴')
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        mod = getattr(node, 'module', None) or ''
                        names = ','.join(a.name for a in node.names)
                        if 'collections' in mod or 'collections' in names:
                            violations.append(f'{fn}:{node.lineno}: collections import')
                    elif (isinstance(node, ast.Subscript)
                          and isinstance(node.value, ast.Name)
                          and node.value.id in self.BUILTIN_GENERICS):
                        violations.append(
                            f'{fn}:{node.lineno}: '
                            f'{node.value.id}[...] 내장 제네릭은 3.9+')
                    elif isinstance(node, ast.NamedExpr):
                        violations.append(f'{fn}:{node.lineno}: walrus는 3.8 미만 비호환')
                    elif hasattr(ast, 'Match') and isinstance(node, getattr(ast, 'Match')):
                        violations.append(f'{fn}:{node.lineno}: match 문은 3.10+')
        self.assertEqual(violations, [], '\n'.join(violations))
        # 검사가 '아무 파일도 못 찾아서' 통과하는 상태를 막는다.
        for expected in ('main.py', os.path.join('minredis', 'mini_redis.py'),
                         os.path.join('minredis', 'cli.py'),
                         os.path.join('tests', 'test_cli.py')):
            self.assertIn(expected, scanned)

    def test_every_file_parses_as_python_38(self):
        """과제가 요구하는 하한(3.8) 파서로 전 파일이 읽히는지 본다.

        AST 노드 검사는 '아는 위반'만 잡는다. feature_version=(3, 8) 파싱은
        match 문·except*·괄호 컨텍스트 매니저처럼 아직 목록에 없는 3.9+
        문법까지 한꺼번에 막는다.
        """
        import ast
        import os

        failures = []
        checked = 0
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames
                           if d != '__pycache__' and not d.startswith('.')]
            for fn in filenames:
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(dirpath, fn)
                with io.open(path, encoding='utf-8') as fh:
                    source = fh.read()
                checked += 1
                try:
                    ast.parse(source, feature_version=(3, 8))
                except SyntaxError as exc:
                    failures.append(f'{os.path.relpath(path, ROOT)}: {exc}')
        self.assertEqual(failures, [], '\n'.join(failures))
        self.assertGreaterEqual(checked, 5)


if __name__ == '__main__':
    unittest.main()
