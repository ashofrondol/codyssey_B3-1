"""Mini Redis 본체.

세 가지 자료구조를 조합해 동작한다.
    - HashMap          : key -> _Entry 매핑 (메인 저장소)
    - DoublyLinkedList : LRU 추적 (앞 = MRU, 뒤 = LRU)
    - MinHeap          : (expire_at, key) 형태의 TTL 만료 시간 우선순위

각 명령 메서드는 결과를 '튜플' 형태로 반환한다. CLI 레이어가 이 튜플을
Redis 스타일 문자열로 변환해 출력한다. 자료구조 계층과 출력 계층을
분리해 두면 테스트하기도 쉽고 출력 형식이 바뀌어도 본체는 안 건드린다.

반환 튜플 종류:
    ('ok',)                      -> "OK"
    ('nil',)                     -> "(nil)"
    ('int', n)                   -> "(integer) n"
    ('bulk', s)                  -> "\"s\""
    ('array', [..])              -> 줄바꿈으로 구분된 목록
    ('info', used, max, evict)   -> INFO memory 출력
    ('error', msg)               -> "(error) msg"
"""

import time

from hashmap import HashMap
from heap import MinHeap
from linked_list import DoublyLinkedList


class _Entry:
    """저장소 내부에서 키 하나를 표현하는 객체."""

    __slots__ = ('key', 'value', 'lru_node', 'expire_at')

    def __init__(self, key, value, lru_node, expire_at=None):
        self.key = key
        self.value = value
        self.lru_node = lru_node  # LRU 리스트에서 이 키를 가리키는 노드(O(1) 제거/이동용)
        self.expire_at = expire_at  # 절대 만료 시각(time.time 기준). None이면 만료 없음


class MiniRedis:
    """Mini Redis 코어 엔진."""

    _OOM_MSG = "OOM command not allowed when used_memory > 'maxmemory'"

    def __init__(self, now_fn=time.time):
        self._store = HashMap()
        self._lru = DoublyLinkedList()
        self._ttl_heap = MinHeap()
        self._maxmemory = 0        # 0이면 무제한
        self._used_memory = 0
        self._evicted_keys = 0
        self._now_fn = now_fn      # 테스트 주입용

    # ---------- helpers ----------

    @staticmethod
    def _utf8_len(s):
        return len(s.encode('utf-8'))

    def _entry_size(self, key, value):
        # 스펙: used_memory = Σ( len(utf8(key)) + len(utf8(value)) )
        return self._utf8_len(key) + self._utf8_len(value)

    def _is_expired(self, entry):
        return entry.expire_at is not None and entry.expire_at <= self._now_fn()

    def _hard_delete(self, key, entry):
        """저장소/LRU에서 엔트리를 제거하고 메모리 사용량을 보정한다.
        TTL 힙의 stale 항목은 lazy deletion으로 추후 정리한다."""
        self._lru.remove_node(entry.lru_node)
        self._store.remove(key)
        self._used_memory -= self._entry_size(key, entry.value)

    def _get_live_entry(self, key):
        """만료된 키는 그 자리에서 제거하고, 살아 있는 엔트리만 반환한다."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            self._hard_delete(key, entry)
            return None
        return entry

    def _purge_expired_via_heap(self):
        """힙의 머리부터 만료된 항목을 정리(lazy deletion).

        같은 키에 EXPIRE를 다시 걸면 힙에 새 항목이 추가되고 옛 항목은 남는다.
        그래서 pop 후에는 항상 '현재 엔트리의 expire_at과 일치하는지' 확인하여
        오래된(stale) 항목을 걸러낸다.
        """
        now = self._now_fn()
        while not self._ttl_heap.is_empty():
            expire_at, key = self._ttl_heap.peek()
            if expire_at > now:
                break
            self._ttl_heap.pop()
            entry = self._store.get(key)
            if entry is None:
                continue  # 이미 DEL 등으로 제거됨
            if entry.expire_at != expire_at:
                continue  # 이미 다른 TTL로 갱신됨 (오래된 항목)
            self._hard_delete(key, entry)

    def _evict_to_fit(self, additional_size):
        """maxmemory 제한 안에 들어갈 때까지 LRU(맨 뒤)부터 제거한다."""
        if self._maxmemory <= 0:
            return
        while (self._used_memory + additional_size > self._maxmemory
               and not self._lru.is_empty()):
            tail_node = self._lru.back()
            victim_key = tail_node.data
            victim = self._store.get(victim_key)
            if victim is None:
                # 방어적 정리: LRU에는 있는데 store에 없는 일은 정상 흐름에선 없어야 하지만
                # 어떤 경로로든 어긋났다면 노드만 제거하고 진행한다.
                self._lru.remove_node(tail_node)
                continue
            self._hard_delete(victim_key, victim)
            self._evicted_keys += 1

    # ---------- commands ----------

    def cmd_set(self, key, value):
        new_size = self._entry_size(key, value)

        # 단일 엔트리 자체가 maxmemory보다 크면 저장하지 않고 OOM
        if self._maxmemory > 0 and new_size > self._maxmemory:
            return ('error', self._OOM_MSG)

        # 기존 키가 있고 만료되지 않았다면 먼저 제거한다.
        # (스펙: 덮어쓰기 시 기존 TTL은 초기화/삭제 → 새 엔트리는 expire_at=None이므로 자연 만족)
        existing = self._get_live_entry(key)
        if existing is not None:
            self._hard_delete(key, existing)

        # 들어올 크기만큼 자리를 만든다(LRU 제거)
        self._evict_to_fit(new_size)

        # 안전망: 모두 비웠는데도 안 들어간다면 OOM (이 분기는 사실상
        # 첫 줄의 단일 엔트리 검사로 이미 걸러진다)
        if self._maxmemory > 0 and self._used_memory + new_size > self._maxmemory:
            return ('error', self._OOM_MSG)

        lru_node = self._lru.insert_front(key)
        entry = _Entry(key, value, lru_node, expire_at=None)
        self._store.put(key, entry)
        self._used_memory += new_size
        return ('ok',)

    def cmd_get(self, key):
        entry = self._get_live_entry(key)
        if entry is None:
            return ('nil',)
        self._lru.move_to_front(entry.lru_node)
        return ('bulk', entry.value)

    def cmd_del(self, key):
        entry = self._get_live_entry(key)
        if entry is None:
            return ('int', 0)
        self._hard_delete(key, entry)
        return ('int', 1)

    def cmd_exists(self, key):
        return ('int', 1 if self._get_live_entry(key) is not None else 0)

    def cmd_dbsize(self):
        self._purge_expired_via_heap()
        return ('int', self._store.size())

    def cmd_keys(self):
        self._purge_expired_via_heap()
        return ('array', self._store.keys())

    def cmd_config_set_maxmemory(self, bytes_value):
        if bytes_value < 0:
            return ('error', 'ERR value is not an integer or out of range')
        self._maxmemory = bytes_value
        # 새 제한이 현재 사용량보다 작으면 즉시 LRU 제거를 수행한다.
        if self._maxmemory > 0:
            self._evict_to_fit(0)
        return ('ok',)

    def cmd_info_memory(self):
        self._purge_expired_via_heap()
        return ('info', self._used_memory, self._maxmemory, self._evicted_keys)

    def cmd_expire(self, key, seconds):
        entry = self._get_live_entry(key)
        if entry is None:
            return ('int', 0)
        if seconds <= 0:
            # 즉시 만료: 존재하던 키를 삭제하고 1 반환
            self._hard_delete(key, entry)
            return ('int', 1)
        expire_at = self._now_fn() + seconds
        entry.expire_at = expire_at
        self._ttl_heap.push((expire_at, key))
        return ('int', 1)

    def cmd_ttl(self, key):
        entry = self._get_live_entry(key)
        if entry is None:
            return ('int', -2)
        if entry.expire_at is None:
            return ('int', -1)
        remaining = entry.expire_at - self._now_fn()
        if remaining < 0:
            return ('int', -2)
        return ('int', int(remaining))
