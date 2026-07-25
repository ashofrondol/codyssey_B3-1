"""Mini Redis 코어 엔진 테스트.

시계를 주입(FakeClock)해 sleep 없이 TTL 만료를 결정적으로 재현한다.
"""

import random
import unittest

from tests.helpers import FakeClock

from mini_redis import MiniRedis


class TestStringCommands(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.r = MiniRedis(now_fn=self.clock)

    def test_set_get(self):
        self.assertEqual(self.r.cmd_set('k', 'v'), ('ok',))
        self.assertEqual(self.r.cmd_get('k'), ('bulk', 'v'))
        self.assertEqual(self.r.cmd_get('missing'), ('nil',))

    def test_del(self):
        self.r.cmd_set('k', 'v')
        self.assertEqual(self.r.cmd_del('k'), ('int', 1))
        self.assertEqual(self.r.cmd_del('k'), ('int', 0))
        self.assertEqual(self.r.cmd_get('k'), ('nil',))

    def test_del_removes_from_data_ttl_and_lru(self):
        self.r.cmd_set('k', 'v')
        self.r.cmd_expire('k', 100)
        self.r.cmd_del('k')
        self.assertEqual(self.r.cmd_dbsize(), ('int', 0))
        self.assertEqual(self.r.cmd_ttl('k'), ('int', -2))
        self.assertEqual(len(self.r._lru), 0)
        self.assertEqual(self.r._used_memory, 0)

    def test_exists_dbsize_keys(self):
        self.assertEqual(self.r.cmd_keys(), ('array', []))
        self.r.cmd_set('a', '1')
        self.r.cmd_set('b', '2')
        self.assertEqual(self.r.cmd_exists('a'), ('int', 1))
        self.assertEqual(self.r.cmd_exists('zz'), ('int', 0))
        self.assertEqual(self.r.cmd_dbsize(), ('int', 2))
        self.assertEqual(sorted(self.r.cmd_keys()[1]), ['a', 'b'])

    def test_set_overwrite_clears_ttl(self):
        """명세: 기존 키를 덮어쓰면 기존 TTL은 초기화(삭제)된다."""
        self.r.cmd_set('k', 'v1')
        self.r.cmd_expire('k', 100)
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 100))
        self.r.cmd_set('k', 'v2')
        self.assertEqual(self.r.cmd_ttl('k'), ('int', -1))
        self.assertEqual(self.r.cmd_get('k'), ('bulk', 'v2'))

    def test_stale_heap_entry_does_not_kill_new_value(self):
        """덮어쓰기 후 힙에 남은 옛 항목이 새 값을 지우면 안 된다."""
        self.r.cmd_set('k', 'v1')
        self.r.cmd_expire('k', 5)
        self.r.cmd_set('k', 'v2')       # TTL 초기화, 힙에는 옛 항목 잔존
        self.clock.advance(10)
        self.assertEqual(self.r.cmd_get('k'), ('bulk', 'v2'))
        self.assertEqual(self.r.cmd_dbsize(), ('int', 1))

    def test_ttl_shortening_takes_effect(self):
        """TTL을 짧게 갱신하면 짧아진 시각에 만료되어야 한다."""
        self.r.cmd_set('k', 'v')
        self.r.cmd_expire('k', 1000)
        self.r.cmd_expire('k', 5)
        self.clock.advance(6)
        self.assertEqual(self.r.cmd_get('k'), ('nil',))


class TestMemoryAccounting(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.r = MiniRedis(now_fn=self.clock)

    def test_used_memory_formula(self):
        self.r.cmd_set('user:1', 'Alice')      # 6 + 5
        self.assertEqual(self.r.cmd_info_memory()[1], 11)

    def test_used_memory_multibyte(self):
        """UTF-8 바이트 길이로 계산해야 한다 (문자 수가 아니라)."""
        self.r.cmd_set('한글키', '값🙂')       # 9 + (3 + 4)
        self.assertEqual(self.r.cmd_info_memory()[1], 16)

    def test_used_memory_after_overwrite_and_delete(self):
        self.r.cmd_set('k', 'aaaa')
        self.r.cmd_set('k', 'bb')
        self.assertEqual(self.r.cmd_info_memory()[1], 3)
        self.r.cmd_del('k')
        self.assertEqual(self.r.cmd_info_memory()[1], 0)

    def test_spec_example_lru_eviction(self):
        """명세 실행 예시를 값 그대로 고정한다."""
        self.assertEqual(self.r.cmd_config_set_maxmemory(30), ('ok',))
        self.r.cmd_set('user:1', 'Alice')      # 11
        self.r.cmd_set('user:2', 'Bob')        # 9
        self.r.cmd_set('user:3', 'Charlie')    # 13 -> 33 초과, user:1 축출
        self.assertEqual(self.r.cmd_get('user:1'), ('nil',))
        self.assertEqual(self.r.cmd_info_memory(), ('info', 22, 30, 1))
        self.assertEqual(sorted(self.r.cmd_keys()[1]), ['user:2', 'user:3'])

    def test_maxmemory_zero_is_unlimited(self):
        self.r.cmd_config_set_maxmemory(0)
        for i in range(100):
            self.r.cmd_set(f'k{i}', 'x' * 50)
        self.assertEqual(self.r.cmd_dbsize(), ('int', 100))
        self.assertEqual(self.r.cmd_info_memory()[3], 0)

    def test_negative_maxmemory_rejected_without_side_effects(self):
        self.r.cmd_config_set_maxmemory(100)
        self.r.cmd_set('k', 'v')
        result = self.r.cmd_config_set_maxmemory(-1)
        self.assertEqual(result[0], 'error')
        self.assertEqual(self.r._maxmemory, 100)
        self.assertEqual(self.r.cmd_get('k'), ('bulk', 'v'))

    def test_single_entry_larger_than_maxmemory_is_oom(self):
        self.r.cmd_config_set_maxmemory(10)
        result = self.r.cmd_set('key', 'x' * 100)
        self.assertEqual(result[0], 'error')
        self.assertIn('OOM', result[1])
        self.assertEqual(self.r.cmd_dbsize(), ('int', 0))

    def test_oom_preserves_existing_value_ttl_and_evicted_count(self):
        """OOM 시 축출을 시도하지 않으므로 기존 상태가 전부 보존된다."""
        self.r.cmd_config_set_maxmemory(20)
        self.r.cmd_set('k', 'small')
        self.r.cmd_expire('k', 100)
        result = self.r.cmd_set('k', 'x' * 100)
        self.assertEqual(result[0], 'error')
        self.assertEqual(self.r.cmd_get('k'), ('bulk', 'small'))
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 100))
        self.assertEqual(self.r.cmd_info_memory()[3], 0)

    def test_lru_order_follows_get(self):
        """GET이 성공하면 그 키가 MRU가 되어 축출 대상에서 벗어난다."""
        self.r.cmd_config_set_maxmemory(12)
        self.r.cmd_set('a', '1')       # 2
        self.r.cmd_set('b', '2')       # 2
        self.r.cmd_get('a')            # a가 MRU로
        self.r.cmd_set('c', 'x' * 9)   # 10 -> 총 14, b가 축출되어야 함
        self.assertEqual(self.r.cmd_get('a'), ('bulk', '1'))
        self.assertEqual(self.r.cmd_get('b'), ('nil',))

    def test_config_set_shrink_evicts_immediately(self):
        self.r.cmd_set('a', 'x' * 9)   # 10
        self.r.cmd_set('b', 'y' * 9)   # 10
        self.r.cmd_config_set_maxmemory(10)
        self.assertEqual(self.r.cmd_info_memory(), ('info', 10, 10, 1))
        self.assertEqual(self.r.cmd_keys()[1], ['b'])

    def test_used_memory_invariant_under_random_ops(self):
        """무작위 연산 후에도 used_memory == Σ(utf8 키 + 값) 이어야 한다."""
        rng = random.Random(20260725)
        keys = [f'k{i}' for i in range(10)] + ['한글', '🙂']
        for _ in range(3000):
            op = rng.random()
            k = rng.choice(keys)
            if op < 0.45:
                self.r.cmd_set(k, 'v' * rng.randint(1, 9))
            elif op < 0.60:
                self.r.cmd_get(k)
            elif op < 0.70:
                self.r.cmd_del(k)
            elif op < 0.80:
                self.r.cmd_expire(k, rng.choice([-1, 0, 1, 3, 60]))
            elif op < 0.85:
                self.r.cmd_config_set_maxmemory(rng.choice([0, 0, 40, 80, 200]))
            elif op < 0.92:
                self.clock.advance(rng.choice([0, 0.5, 2, 5]))
            else:
                self.r.cmd_keys()
                self.r.cmd_dbsize()

            expected = 0
            for key in self.r._store.keys():
                entry = self.r._store.get(key)
                expected += (len(key.encode('utf-8'))
                             + len(entry.value.encode('utf-8')))
            self.assertEqual(self.r._used_memory, expected)
            self.assertEqual(len(self.r._lru), self.r._store.size())


class TestTTL(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.r = MiniRedis(now_fn=self.clock)

    def test_ttl_return_codes(self):
        self.assertEqual(self.r.cmd_ttl('missing'), ('int', -2))
        self.r.cmd_set('k', 'v')
        self.assertEqual(self.r.cmd_ttl('k'), ('int', -1))
        self.r.cmd_expire('k', 10)
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 10))
        self.clock.advance(4)
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 6))

    def test_expire_on_missing_key(self):
        self.assertEqual(self.r.cmd_expire('missing', 10), ('int', 0))

    def test_expire_zero_or_negative_deletes_immediately(self):
        for seconds in (0, -1):
            self.r.cmd_set('k', 'v')
            self.assertEqual(self.r.cmd_expire('k', seconds), ('int', 1))
            self.assertEqual(self.r.cmd_get('k'), ('nil',))
            self.assertEqual(self.r.cmd_ttl('k'), ('int', -2))
            self.assertEqual(self.r.cmd_dbsize(), ('int', 0))

    def test_expired_key_behaves_as_absent(self):
        self.r.cmd_set('k', 'v')
        self.r.cmd_expire('k', 3)
        self.clock.advance(4)
        self.assertEqual(self.r.cmd_get('k'), ('nil',))
        self.assertEqual(self.r.cmd_exists('k'), ('int', 0))
        self.assertEqual(self.r.cmd_del('k'), ('int', 0))
        self.assertEqual(self.r.cmd_ttl('k'), ('int', -2))

    def test_expired_key_hidden_from_aggregates_without_access(self):
        """한 번도 접근하지 않은 만료 키가 집계에 잡히면 안 된다."""
        self.r.cmd_set('a', 'AAAA')
        self.r.cmd_set('b', 'BBBB')
        self.r.cmd_expire('a', 1)
        self.clock.advance(2)
        self.assertEqual(self.r.cmd_dbsize(), ('int', 1))
        self.assertEqual(self.r.cmd_keys()[1], ['b'])
        self.assertEqual(self.r.cmd_info_memory()[1], 5)

    def test_expired_get_does_not_refresh_lru(self):
        """만료로 삭제된 경로에서는 LRU 갱신이 없어야 한다."""
        self.r.cmd_config_set_maxmemory(0)
        self.r.cmd_set('a', '1')
        self.r.cmd_expire('a', 1)
        self.clock.advance(2)
        self.assertEqual(self.r.cmd_get('a'), ('nil',))
        self.assertEqual(len(self.r._lru), 0)

    def test_expiry_boundary_is_inclusive(self):
        """expire_at == now 는 '만료됨'이다 (<= 이지 < 가 아니다)."""
        self.r.cmd_set('k', 'v')
        self.r.cmd_expire('k', 3)
        self.clock.advance(2.999)
        self.assertEqual(self.r.cmd_get('k'), ('bulk', 'v'))
        self.clock.advance(0.001)                 # 정확히 만료 시각
        self.assertEqual(self.r.cmd_get('k'), ('nil',))
        self.assertEqual(self.r.cmd_ttl('k'), ('int', -2))

    def test_ttl_floors_remaining_seconds(self):
        """남은 시간은 내림한다. 살아 있는 키가 0을 반환할 수 있다."""
        self.r.cmd_set('k', 'v')
        self.r.cmd_expire('k', 3)
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 3))
        self.clock.advance(0.5)
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 2))
        self.clock.advance(2.4)                   # 남은 0.1초 — 살아 있음
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 0))
        self.assertEqual(self.r.cmd_get('k'), ('bulk', 'v'))

    def test_expire_on_already_expired_key_returns_zero(self):
        self.r.cmd_set('k', 'v')
        self.r.cmd_expire('k', 1)
        self.clock.advance(2)
        self.assertEqual(self.r.cmd_expire('k', 100), ('int', 0))

    def test_ttl_heap_is_compacted(self):
        """같은 키에 EXPIRE를 반복해도 힙이 무한정 커지지 않아야 한다."""
        self.r.cmd_set('k', 'v')
        for _ in range(5000):
            self.r.cmd_expire('k', 3600)
        self.assertLessEqual(self.r._ttl_heap.size(), 32)
        self.assertEqual(self.r.cmd_ttl('k'), ('int', 3600))

    def test_ttl_heap_bounded_without_any_purge_command(self):
        """SET/DBSIZE/KEYS/INFO를 한 번도 섞지 않는 GET+EXPIRE 워크로드에서도
        힙이 상한 안에 머물러야 한다 (세션 TTL 연장 패턴)."""
        for i in range(10):
            self.r.cmd_set(f's{i}', 'payload')
        for _ in range(2000):
            for i in range(10):
                self.r.cmd_get(f's{i}')
                self.r.cmd_expire(f's{i}', 1800)
        self.assertLessEqual(self.r._ttl_heap.size(), 32)
        self.assertEqual(self.r.cmd_ttl('s0'), ('int', 1800))

    def test_compaction_threshold_tracks_ttl_keys_not_all_keys(self):
        """TTL 없는 키가 대다수여도 힙 상한이 그 수만큼 부풀지 않아야 한다."""
        for i in range(500):
            self.r.cmd_set(f'plain{i}', 'v')     # TTL 없음
        self.r.cmd_set('hot', 'v')
        for _ in range(3000):
            self.r.cmd_expire('hot', 3600)
        self.assertLessEqual(self.r._ttl_heap.size(), 32)

    def test_unlimited_mode_set_does_not_stall_on_mass_expiry(self):
        """무제한 모드 SET이 '그동안 만료된 키 전부 회수'를 떠안지 않아야 한다."""
        for i in range(3000):
            self.r.cmd_set(f'k{i}', 'v')
            self.r.cmd_expire(f'k{i}', 1)
        self.clock.advance(5)                     # 3000개 동시 만료
        before = self.r._ttl_heap.size()
        self.r.cmd_set('newkey', 'v')             # O(1)이어야 한다
        self.assertGreaterEqual(self.r._ttl_heap.size(), before - 1)
        # 회수 책임은 조회 명령이 진다
        self.assertEqual(self.r.cmd_dbsize(), ('int', 1))

    def test_bounded_mode_still_purges_before_evicting(self):
        """maxmemory > 0에서는 축출 전 만료 회수가 그대로 유지되어야 한다."""
        self.r.cmd_config_set_maxmemory(30)
        self.r.cmd_set('live', '123456')
        self.r.cmd_set('dead', '123456')
        self.r.cmd_expire('dead', 1)
        self.clock.advance(2)
        self.r.cmd_set('new', '123456789012')
        self.assertEqual(self.r.cmd_get('live'), ('bulk', '123456'))
        self.assertEqual(self.r.cmd_info_memory()[3], 0)

    def test_ttl_heap_drains_when_keys_expire(self):
        for i in range(200):
            self.r.cmd_set(f'k{i}', 'v')
            self.r.cmd_expire(f'k{i}', 1)
        self.clock.advance(5)
        self.assertEqual(self.r.cmd_dbsize(), ('int', 0))
        self.assertEqual(self.r._ttl_heap.size(), 0)


class TestExpiryEvictionRegression(unittest.TestCase):
    """만료 키가 축출 판정을 오염시키던 버그의 회귀 테스트."""

    def test_eviction_purges_expired_before_evicting_live_keys(self):
        clock = FakeClock()
        r = MiniRedis(now_fn=clock)
        r.cmd_config_set_maxmemory(30)
        r.cmd_set('user:2', 'Bob')       # 9,  LRU 꼬리 — 살아남아야 함
        r.cmd_set('user:1', 'Alice')     # 11, MRU
        r.cmd_expire('user:1', 5)
        clock.advance(10)                # user:1 만료 (아직 미회수)
        r.cmd_set('user:3', 'Charlie')   # 13
        self.assertEqual(r.cmd_get('user:2'), ('bulk', 'Bob'))
        self.assertEqual(r.cmd_info_memory()[3], 0)   # 만료는 evicted가 아니다

    def test_config_set_purges_expired_before_evicting(self):
        clock = FakeClock()
        r = MiniRedis(now_fn=clock)
        r.cmd_set('live', '123456')      # 10
        r.cmd_set('dead', '123456')      # 10
        r.cmd_expire('dead', 1)
        clock.advance(2)
        r.cmd_config_set_maxmemory(10)
        self.assertEqual(r.cmd_get('live'), ('bulk', '123456'))
        self.assertEqual(r.cmd_info_memory(), ('info', 10, 10, 0))

    def test_readonly_commands_do_not_change_outcome(self):
        """조회 명령의 유무가 어떤 키가 살아남는지를 바꾸면 안 된다."""
        def run(with_probe):
            clock = FakeClock()
            r = MiniRedis(now_fn=clock)
            r.cmd_config_set_maxmemory(30)
            r.cmd_set('live', '123456')
            r.cmd_set('dead', '123456')
            r.cmd_expire('dead', 1)
            clock.advance(2)
            if with_probe:
                r.cmd_dbsize()
            r.cmd_set('new', '123456789012')
            return sorted(r.cmd_keys()[1]), r.cmd_info_memory()

        self.assertEqual(run(True), run(False))

    def test_pure_lru_eviction_still_counts(self):
        """TTL과 무관한 순수 축출은 여전히 evicted_keys를 올려야 한다."""
        clock = FakeClock()
        r = MiniRedis(now_fn=clock)
        r.cmd_config_set_maxmemory(10)
        r.cmd_set('a', 'x' * 9)
        r.cmd_set('b', 'y' * 9)
        self.assertEqual(r.cmd_info_memory()[3], 1)
        self.assertEqual(r.cmd_get('a'), ('nil',))


if __name__ == '__main__':
    unittest.main()
