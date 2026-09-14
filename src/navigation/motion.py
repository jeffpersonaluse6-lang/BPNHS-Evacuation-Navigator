"""Deadline scheduling: render cost doesn't get added to the frame interval."""

from dataclasses import dataclass


@dataclass
class MotionClock:
    previous: float

    def delay(self,now,interval):return max(0,interval-(now-self.previous))

    def advance(self,now):
        elapsed=max(0,now-self.previous);self.previous=now
        # Ignore a window suspend/debugger pause, not ordinary dropped frames.
        return 0. if elapsed>.5 else elapsed
