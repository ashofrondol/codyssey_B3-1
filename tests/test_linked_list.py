"""이중 연결 리스트 단위 테스트."""

import unittest

from tests.helpers import FakeClock  # noqa: F401  (sys.path 부트스트랩)

from linked_list import DoublyLinkedList, Node


class TestDoublyLinkedList(unittest.TestCase):

    def setUp(self):
        self.dll = DoublyLinkedList()

    # --- 기본 상태 ---

    def test_empty_list(self):
        self.assertTrue(self.dll.is_empty())
        self.assertEqual(len(self.dll), 0)
        self.assertIsNone(self.dll.front())
        self.assertIsNone(self.dll.back())
        self.assertIsNone(self.dll.remove_front())
        self.assertIsNone(self.dll.remove_back())

    def test_required_methods_exist(self):
        """명세가 열거한 필수 메서드 6종이 모두 존재해야 한다."""
        for name in ('insert_front', 'insert_back', 'remove_front',
                     'remove_back', 'remove_node', 'move_to_front'):
            self.assertTrue(callable(getattr(self.dll, name, None)), name)

    def test_node_has_prev_next_data(self):
        node = self.dll.insert_front('x')
        for field in ('prev', 'next', 'data'):
            self.assertTrue(hasattr(node, field), field)
        self.assertEqual(node.data, 'x')

    # --- 삽입/삭제 ---

    def test_insert_front_and_back_order(self):
        self.dll.insert_front('b')
        self.dll.insert_front('a')
        self.dll.insert_back('c')
        self.assertEqual(list(self.dll.iter_data()), ['a', 'b', 'c'])
        self.assertEqual(len(self.dll), 3)

    def test_remove_front_and_back(self):
        for ch in 'abc':
            self.dll.insert_back(ch)
        self.assertEqual(self.dll.remove_front(), 'a')
        self.assertEqual(self.dll.remove_back(), 'c')
        self.assertEqual(list(self.dll.iter_data()), ['b'])

    def test_remove_node_middle_first_last(self):
        nodes = [self.dll.insert_back(ch) for ch in 'abcd']
        self.assertEqual(self.dll.remove_node(nodes[1]), 'b')      # 중간
        self.assertEqual(self.dll.remove_node(nodes[0]), 'a')      # 첫
        self.assertEqual(self.dll.remove_node(nodes[3]), 'd')      # 마지막
        self.assertEqual(list(self.dll.iter_data()), ['c'])
        self.assertEqual(len(self.dll), 1)

    def test_single_node_removal(self):
        node = self.dll.insert_front('only')
        self.assertEqual(self.dll.remove_node(node), 'only')
        self.assertTrue(self.dll.is_empty())

    # --- 계약 방어 ---

    def test_remove_node_twice_is_noop(self):
        """이미 제거된 노드를 다시 제거해도 크래시하지 않고 _size도 안 깨진다."""
        node = self.dll.insert_front('x')
        self.dll.insert_front('y')
        self.assertEqual(self.dll.remove_node(node), 'x')
        self.assertIsNone(self.dll.remove_node(node))
        self.assertEqual(len(self.dll), 1)

    def test_remove_node_from_other_list_is_noop(self):
        """다른 리스트의 노드를 넘겨도 양쪽 _size가 손상되지 않는다."""
        other = DoublyLinkedList()
        foreign = other.insert_front('foreign')
        self.dll.insert_front('mine')
        self.assertIsNone(self.dll.remove_node(foreign))
        self.assertEqual(len(self.dll), 1)
        self.assertEqual(len(other), 1)

    def test_remove_node_none_and_detached(self):
        self.assertIsNone(self.dll.remove_node(None))
        self.assertIsNone(self.dll.remove_node(Node('detached')))
        self.assertEqual(len(self.dll), 0)

    # --- move_to_front ---

    def test_move_to_front(self):
        nodes = [self.dll.insert_back(ch) for ch in 'abc']
        self.dll.move_to_front(nodes[2])
        self.assertEqual(list(self.dll.iter_data()), ['c', 'a', 'b'])

    def test_move_to_front_is_idempotent_on_head(self):
        nodes = [self.dll.insert_back(ch) for ch in 'ab']
        self.dll.move_to_front(nodes[0])
        self.dll.move_to_front(nodes[0])
        self.assertEqual(list(self.dll.iter_data()), ['a', 'b'])
        self.assertEqual(len(self.dll), 2)

    def test_move_to_front_ignores_foreign_and_none(self):
        other = DoublyLinkedList()
        foreign = other.insert_front('foreign')
        self.dll.insert_front('mine')
        self.dll.move_to_front(foreign)   # 무시되어야 함
        self.dll.move_to_front(None)
        self.assertEqual(list(self.dll.iter_data()), ['mine'])
        self.assertEqual(len(other), 1)

    # --- 순회 안전성 ---

    def test_iter_nodes_safe_under_removal(self):
        nodes = [self.dll.insert_back(i) for i in range(5)]
        for node in self.dll.iter_nodes():
            if node.data % 2 == 0:
                self.dll.remove_node(node)
        self.assertEqual(list(self.dll.iter_data()), [1, 3])
        self.assertEqual(len(self.dll), 2)
        del nodes


if __name__ == '__main__':
    unittest.main()
