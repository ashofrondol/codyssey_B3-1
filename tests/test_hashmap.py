"""해시맵 단위 테스트."""

import unittest

from tests.helpers import FakeClock  # noqa: F401  (sys.path 부트스트랩)

from hashmap import HashMap


class TestHashMap(unittest.TestCase):

    def setUp(self):
        self.hm = HashMap()

    def test_required_methods_exist(self):
        """명세 필수: put/get/remove/contains/keys/size."""
        for name in ('put', 'get', 'remove', 'contains', 'keys', 'size'):
            self.assertTrue(callable(getattr(self.hm, name, None)), name)

    # --- 기본 동작 ---

    def test_put_get_remove(self):
        self.assertTrue(self.hm.put('a', 1))          # 신규
        self.assertEqual(self.hm.get('a'), 1)
        self.assertFalse(self.hm.put('a', 2))         # 덮어쓰기
        self.assertEqual(self.hm.get('a'), 2)
        self.assertEqual(self.hm.size(), 1)
        self.assertEqual(self.hm.remove('a'), 2)
        self.assertIsNone(self.hm.get('a'))
        self.assertEqual(self.hm.size(), 0)

    def test_get_default_and_contains_with_none_value(self):
        """값이 None이어도 '존재'는 True여야 한다 (get만으로는 구분 불가)."""
        self.hm.put('k', None)
        self.assertIsNone(self.hm.get('k'))
        self.assertIsNone(self.hm.get('missing', None))
        self.assertEqual(self.hm.get('missing', 'default'), 'default')
        self.assertTrue(self.hm.contains('k'))
        self.assertFalse(self.hm.contains('missing'))

    def test_remove_missing_returns_none(self):
        self.assertIsNone(self.hm.remove('nope'))
        self.assertEqual(self.hm.size(), 0)

    def test_keys_matches_size(self):
        for i in range(50):
            self.hm.put(f'k{i}', i)
        keys = self.hm.keys()
        self.assertEqual(len(keys), self.hm.size())
        self.assertEqual(sorted(keys), sorted(f'k{i}' for i in range(50)))

    def test_unicode_keys(self):
        for key in ('한글키', '🙂', 'ключ', 'a'):
            self.hm.put(key, key.upper())
        self.assertEqual(self.hm.get('한글키'), '한글키'.upper())
        self.assertEqual(self.hm.get('🙂'), '🙂')
        self.assertEqual(self.hm.size(), 4)

    # --- 로드 팩터 ---

    def test_grow_points_are_load_factor_over_075(self):
        """'0.75 초과' 규칙: capacity 8이면 6개까지 유지, 7번째에 확장."""
        grow_points = []
        prev = self.hm.capacity()
        for i in range(1, 60):
            self.hm.put(f'k{i}', i)
            if self.hm.capacity() != prev:
                grow_points.append((i, prev, self.hm.capacity()))
                prev = self.hm.capacity()
        self.assertEqual([g[0] for g in grow_points], [7, 13, 25, 49])
        self.assertEqual([g[2] for g in grow_points], [16, 32, 64, 128])

    def test_all_keys_survive_resize(self):
        for i in range(200):
            self.hm.put(f'key{i}', i * 2)
        self.assertGreater(self.hm.capacity(), 8)
        for i in range(200):
            self.assertEqual(self.hm.get(f'key{i}'), i * 2)

    def test_shrink_after_bulk_removal(self):
        """대량 삭제 후 버킷 테이블이 다시 줄어들어야 한다."""
        for i in range(200):
            self.hm.put(f'k{i}', i)
        grown = self.hm.capacity()
        self.assertGreaterEqual(grown, 256)
        for i in range(197):
            self.hm.remove(f'k{i}')
        self.assertEqual(self.hm.size(), 3)
        self.assertLess(self.hm.capacity(), grown)
        self.assertGreaterEqual(self.hm.capacity(), 8)
        for i in range(197, 200):
            self.assertEqual(self.hm.get(f'k{i}'), i)

    def test_shrink_target_is_pinned(self):
        """축소 목표 용량을 고정한다 (_SHRINK_FACTOR가 바뀌면 실패)."""
        for i in range(200):
            self.hm.put(f'k{i}', i)
        self.assertEqual(self.hm.capacity(), 512)
        for i in range(197):
            self.hm.remove(f'k{i}')
        # size 3 -> 0.1875 임계로 8까지 내려가야 한다 (3 < 16*0.1875=3.0 은 거짓이므로 16에서 멈춤)
        self.assertEqual(self.hm.capacity(), 16)
        self.hm.remove('k197')
        self.assertEqual(self.hm.size(), 2)
        self.assertEqual(self.hm.capacity(), 8)

    def test_shrink_never_below_initial_capacity(self):
        self.hm.put('a', 1)
        self.hm.remove('a')
        self.assertEqual(self.hm.capacity(), 8)

    def test_no_shrink_grow_oscillation(self):
        """축소 직후 재확장이 반복되지 않아야 한다."""
        for i in range(100):
            self.hm.put(f'k{i}', i)
        distinct = []   # 금지된 set 대신 리스트로 중복 제거 (테스트도 제약을 지킨다)
        for i in range(100):
            self.hm.remove(f'k{i}')
            self.hm.put(f'k{i}', i)
            cap = self.hm.capacity()
            if cap not in distinct:
                distinct.append(cap)
        self.assertLessEqual(len(distinct), 2)

    # --- 체이닝 ---

    def test_collision_chaining(self):
        """같은 버킷에 들어가는 키들을 강제로 만들어 체인 동작을 확인한다."""
        capacity = self.hm.capacity()
        target = self.hm._index('seed', capacity)
        colliding = []
        i = 0
        while len(colliding) < 3:
            key = f'c{i}'
            if self.hm._index(key, capacity) == target:
                colliding.append(key)
            i += 1
            if i > 100000:
                self.skipTest('충돌 키를 찾지 못함')

        for n, key in enumerate(colliding):
            self.hm.put(key, n)
        # 확장이 일어나면 버킷이 흩어지므로 3개까지만 넣어 capacity 8을 유지
        self.assertEqual(self.hm.capacity(), capacity)
        bucket = self.hm._buckets[target]
        self.assertEqual(len(bucket), 3)
        for n, key in enumerate(colliding):
            self.assertEqual(self.hm.get(key), n)
        # 체인 중간 삭제 후에도 나머지가 살아 있어야 한다
        self.hm.remove(colliding[1])
        self.assertIsNone(self.hm.get(colliding[1]))
        self.assertEqual(self.hm.get(colliding[0]), 0)
        self.assertEqual(self.hm.get(colliding[2]), 2)

    def test_hash_is_deterministic_and_bounded(self):
        h1 = self.hm._hash('user:1')
        h2 = self.hm._hash('user:1')
        self.assertEqual(h1, h2)
        self.assertTrue(0 <= h1 < (1 << 64))
        self.assertNotEqual(self.hm._hash('a'), self.hm._hash('b'))

    def test_hash_distribution_is_reasonable(self):
        """1000개 키를 넣었을 때 최장 체인이 과도하게 길지 않아야 한다."""
        for i in range(1000):
            self.hm.put(f'user:{i}', i)
        longest = max(len(b) for b in self.hm._buckets)
        self.assertLessEqual(longest, 6)


if __name__ == '__main__':
    unittest.main()
