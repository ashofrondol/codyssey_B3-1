"""README 가 코드를 가리키는 좌표가 실제로 존재하는지 검사한다.

이 저장소의 `0.10 과제 수행 점검` 은 판정 근거를 코드 좌표로 적는다.
처음에는 `파일:줄번호` 였는데, 코드를 한 줄 옮길 때마다 문서가 조용히
거짓이 되었다 — 줄번호는 리팩터링에 견디지 못하는 좌표다.

그래서 좌표를 `파일#심볼` 로 바꾸고, 그 좌표가 유효한지를 여기서 검사한다.
문서에만 적힌 규칙은 규칙이 아니라 희망이다. 이제 코드를 옮기면 문서가
빨간불이 된다.

검사 범위: `### 0.10` 이후. 그 앞은 과제 원문(명세)이고, 거기 나오는
`hash_map.py` 같은 이름은 이 저장소의 파일이 아니라 예시다.
"""

import ast
import io
import os
import re
import unittest

from tests.helpers import ROOT

# `minredis/mini_redis.py#cmd_ttl,cmd_expire` 형태의 인라인 코드 스팬
_SYMBOL_REF = re.compile(r'`([\w/]+\.py)#([\w.,]+)`')
# 마크다운 링크의 상대 경로 대상
_LINK = re.compile(r'\]\(([^)\s]+)\)')
_EVIDENCE_HEADING = '### 0.10 '


def _readme():
    with io.open(os.path.join(ROOT, 'README.md'), encoding='utf-8') as fh:
        return fh.read()


def _defined_names(path):
    """파일이 정의하는 이름들 — 자격 이름과 짧은 이름을 모두 포함한다."""
    with io.open(path, encoding='utf-8') as fh:
        tree = ast.parse(fh.read())
    names = []

    def walk(node, prefix, in_func):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                qualified = prefix + child.name
                names.append(qualified)
                names.append(child.name)
                walk(child, qualified + '.',
                     in_func or not isinstance(child, ast.ClassDef))
            elif not in_func and isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = (child.targets if isinstance(child, ast.Assign)
                           else [child.target])
                for target in targets:
                    if isinstance(target, ast.Name):
                        names.append(prefix + target.id)
                        names.append(target.id)

    walk(tree, '', False)
    return names


class TestReadmeCodeReferences(unittest.TestCase):

    def setUp(self):
        text = _readme()
        self.evidence = text[text.index(_EVIDENCE_HEADING):]

    def test_every_symbol_reference_resolves(self):
        refs = _SYMBOL_REF.findall(self.evidence)
        # 좌표가 통째로 사라지면(= 아무것도 검사하지 않으면) 그것도 실패다.
        self.assertGreaterEqual(len(refs), 50,
                                'README 의 코드 근거 좌표가 사라졌다')
        broken = []
        for rel_path, symbols in refs:
            full = os.path.join(ROOT, rel_path)
            if not os.path.isfile(full):
                broken.append(f'{rel_path}: 파일 없음')
                continue
            defined = _defined_names(full)
            for symbol in symbols.split(','):
                if symbol and symbol not in defined:
                    broken.append(f'{rel_path}#{symbol}: 심볼 없음')
        self.assertEqual(broken, [], '\n'.join(broken))

    def test_every_relative_link_target_exists(self):
        checked = 0
        broken = []
        for target in _LINK.findall(_readme()):
            if target.startswith(('http://', 'https://', 'mailto:', '#')):
                continue
            checked += 1
            if not os.path.exists(os.path.join(ROOT, target)):
                broken.append(target)
        self.assertEqual(broken, [], '\n'.join(broken))
        self.assertGreaterEqual(checked, 10)

    def test_run_command_in_readme_still_exists(self):
        """채점 실행 경로(`python main.py`)가 문서와 저장소 양쪽에 있어야 한다."""
        self.assertIn('python main.py', _readme())
        self.assertTrue(os.path.isfile(os.path.join(ROOT, 'main.py')))


if __name__ == '__main__':
    unittest.main()
