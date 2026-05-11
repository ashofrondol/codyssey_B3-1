"""체이닝(chaining) 방식으로 구현한 해시맵.

각 버킷은 이중 연결 리스트(DoublyLinkedList)를 사용해 충돌을 해결한다.
로드 팩터(저장된 키 개수 / 버킷 개수)가 0.75를 넘으면 버킷을 2배로
늘려서 다시 재배치(rehash)한다.

내장 dict 사용은 금지되어 있으므로, 버킷 테이블 자체는 '고정 길이
인덱스 접근 배열' 용도로 파이썬 list를 사용한다.
"""

from linked_list import DoublyLinkedList


class HashMap:
    """문자열 키 기반의 해시맵.

    충돌 해결: 체이닝(같은 버킷 안에서 이중 연결 리스트로 노드 연결).
    로드 팩터가 0.75를 넘으면 버킷 수를 2배로 확장한다.
    """

    _INITIAL_CAPACITY = 8
    _LOAD_FACTOR = 0.75

    # FNV-1a 해시 상수(64비트)
    _FNV_OFFSET = 0xcbf29ce484222325
    _FNV_PRIME = 0x100000001b3
    _MASK64 = (1 << 64) - 1

    def __init__(self):
        self._capacity = self._INITIAL_CAPACITY
        self._size = 0
        self._buckets = self._make_buckets(self._capacity)

    # ------- public API -------

    def put(self, key, value):
        """key에 value를 저장한다. 같은 키가 있으면 덮어쓴다."""
        bucket = self._buckets[self._index(key, self._capacity)]
        node = self._find_in_bucket(bucket, key)
        if node is not None:
            node.data = (key, value)
            return False  # 신규가 아님
        bucket.insert_back((key, value))
        self._size += 1
        if self._size > self._capacity * self._LOAD_FACTOR:
            self._resize(self._capacity * 2)
        return True

    def get(self, key, default=None):
        """key의 value를 반환. 없으면 default."""
        bucket = self._buckets[self._index(key, self._capacity)]
        node = self._find_in_bucket(bucket, key)
        if node is None:
            return default
        return node.data[1]

    def remove(self, key):
        """key를 제거하고 그 value를 반환. 없으면 None."""
        bucket = self._buckets[self._index(key, self._capacity)]
        node = self._find_in_bucket(bucket, key)
        if node is None:
            return None
        _, value = node.data
        bucket.remove_node(node)
        self._size -= 1
        return value

    def contains(self, key):
        bucket = self._buckets[self._index(key, self._capacity)]
        return self._find_in_bucket(bucket, key) is not None

    def keys(self):
        """저장된 모든 key를 리스트로 반환(순서 보장 없음)."""
        result = []
        for bucket in self._buckets:
            for data in bucket.iter_data():
                result.append(data[0])
        return result

    def size(self):
        return self._size

    def __len__(self):
        return self._size

    # ------- internals -------

    def _hash(self, key):
        """FNV-1a 해시 함수(64비트).

        문자열을 UTF-8 바이트로 변환한 뒤 각 바이트마다:
            h = (h XOR byte) * FNV_PRIME (mod 2^64)
        를 반복해서 분포가 좋은 해시값을 얻는다.
        """
        if isinstance(key, str):
            data = key.encode('utf-8')
        elif isinstance(key, (bytes, bytearray)):
            data = bytes(key)
        else:
            data = str(key).encode('utf-8')
        h = self._FNV_OFFSET
        for byte in data:
            h ^= byte
            h = (h * self._FNV_PRIME) & self._MASK64
        return h

    def _index(self, key, capacity):
        return self._hash(key) % capacity

    @staticmethod
    def _make_buckets(capacity):
        # list는 '고정 길이 인덱스 접근 배열' 용도로만 사용한다.
        # 키-값 저장 자료구조로 사용하는 것은 금지된 영역.
        buckets = [None] * capacity
        for i in range(capacity):
            buckets[i] = DoublyLinkedList()
        return buckets

    @staticmethod
    def _find_in_bucket(bucket, key):
        """버킷(연결 리스트) 안에서 key를 가진 노드를 찾는다."""
        for node in bucket.iter_nodes():
            if node.data[0] == key:
                return node
        return None

    def _resize(self, new_capacity):
        """버킷 테이블을 new_capacity 크기로 다시 만들고 모든 키를 재배치한다."""
        new_buckets = self._make_buckets(new_capacity)
        for bucket in self._buckets:
            for data in bucket.iter_data():
                key, _ = data
                idx = self._hash(key) % new_capacity
                new_buckets[idx].insert_back(data)
        self._buckets = new_buckets
        self._capacity = new_capacity
