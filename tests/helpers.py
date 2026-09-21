"""테스트 공용 도우미.

프로젝트 루트를 sys.path에 넣어, 어느 디렉터리에서 discover를 돌리든
`from minredis import MiniRedis`가 동작하게 한다.
"""

import os
import sys

# 저장소 루트. 제약 검사(TestConstraints)가 훑을 범위이기도 하다.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FakeClock:
    """time.time() 대체용 수동 시계.

    MiniRedis(now_fn=clock)로 주입하면 sleep 없이 TTL 만료를 결정적으로
    재현할 수 있다. 실제 시계에 의존하는 테스트는 느리고 불안정하다.
    """

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        """시계를 앞으로 감는다."""
        self.t += seconds


class DriftingClock:
    """읽을 때마다 조금씩 앞으로 흐르는 시계.

    FakeClock은 advance()를 부르기 전까지 멈춰 있다. 멈춘 시계 아래에서는
    "한 명령이 시계를 두 번 읽는" 버그가 두 읽기를 같은 값으로 만들어
    영원히 보이지 않는다 — 실제 time.time()은 절대 멈추지 않는데도.

    이 시계는 호출마다 step초씩 흐르므로, 만료 경계 근처에서 시계를 두 번
    읽는 코드가 있으면 두 읽기가 경계를 사이에 두고 갈라지고 테스트가 깨진다.
    reads 카운터는 "한 명령은 시계를 한 번만 읽는다"를 직접 단언할 때 쓴다.

    step은 명령 하나가 실제로 소비하는 시간이 아니라 '읽기 사이에 시간이
    흐른다'는 사실만 재현하는 값이다. 경계 테스트가 결정적으로 돌도록
    호출자가 step보다 작은 여유를 직접 잡는다.
    """

    def __init__(self, t=1000.0, step=0.25):
        self.t = t
        self.step = step
        self.reads = 0

    def __call__(self):
        now = self.t
        self.t += self.step
        self.reads += 1
        return now

    def advance(self, seconds):
        """시계를 앞으로 감는다."""
        self.t += seconds
