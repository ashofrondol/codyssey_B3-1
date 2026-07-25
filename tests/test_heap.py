"""최소 힙 단위 테스트."""

import random
import unittest

from tests.helpers import FakeClock  # noqa: F401  (sys.path 부트스트랩)

from heap import MinHeap


class TestMinHeap(unittest.TestCase):

    def setUp(self):
        self.heap = MinHeap()

    def test_required_methods_exist(self):
        """명세 필수: push/pop/peek/size + _heapify_up/_heapify_down."""
        for name in ('push', 'pop', 'peek', 'size',
                     '_heapify_up', '_heapify_down'):
            self.assertTrue(callable(getattr(self.heap, name, None)), name)

    def test_empty_heap(self):
        self.assertTrue(self.heap.is_empty())
        self.assertEqual(self.heap.size(), 0)
        self.assertIsNone(self.heap.peek())
        self.assertIsNone(self.heap.pop())

    def test_peek_does_not_remove(self):
        self.heap.push(3)
        self.heap.push(1)
        self.assertEqual(self.heap.peek(), 1)
        self.assertEqual(self.heap.size(), 2)

    def test_pop_order_matches_sorted(self):
        rng = random.Random(20260725)
        values = [rng.randint(-10_000, 10_000) for _ in range(500)]
        for v in values:
            self.heap.push(v)
        popped = [self.heap.pop() for _ in range(len(values))]
        self.assertEqual(popped, sorted(values))
        self.assertTrue(self.heap.is_empty())

    def test_heap_invariant_holds_during_mixed_ops(self):
        """무작위 push/pop 중에도 부모 <= 자식 불변식이 유지되어야 한다."""
        rng = random.Random(7)
        for _ in range(2000):
            if self.heap.is_empty() or rng.random() < 0.6:
                self.heap.push(rng.randint(0, 999))
            else:
                self.heap.pop()
            data = self.heap._data
            for i in range(1, len(data)):
                self.assertLessEqual(data[(i - 1) // 2], data[i])

    def test_expire_at_key_tuples(self):
        """(expire_at, key) 튜플을 만료 시각 순으로 꺼낼 수 있어야 한다."""
        for item in [(300.0, 'c'), (100.0, 'a'), (200.0, 'b')]:
            self.heap.push(item)
        self.assertEqual(self.heap.peek(), (100.0, 'a'))
        self.assertEqual([self.heap.pop()[1] for _ in range(3)],
                         ['a', 'b', 'c'])

    def test_equal_expire_at_falls_back_to_key_compare(self):
        """만료 시각이 같으면 튜플 두 번째 요소(키 문자열)로 비교된다."""
        self.heap.push((100.0, 'zebra'))
        self.heap.push((100.0, 'apple'))
        self.assertEqual(self.heap.pop(), (100.0, 'apple'))

    def test_duplicates(self):
        for v in [5, 5, 5, 1, 5]:
            self.heap.push(v)
        self.assertEqual([self.heap.pop() for _ in range(5)], [1, 5, 5, 5, 5])


if __name__ == '__main__':
    unittest.main()
