import asyncio
import time
from typing import Tuple, Dict
from .base import RobotAdapter, RobotPhysicalState

class MockRobotAdapter:
    """Mock implementation for Person B to develop against without Gazebo."""
    
    def __init__(self):
        self.states: Dict[str, RobotPhysicalState] = {}
        
    async def navigate(self, robot_id: str, waypoint: Tuple[float, float, float]) -> bool:
        if robot_id not in self.states:
            self.states[robot_id] = RobotPhysicalState(
                robot_id=robot_id, pose=(0, 0, 0), velocity=(0, 0, 0),
                nav_state="NAVIGATING", battery=1.0, timestamp=time.time()
            )
        self.states[robot_id].nav_state = "NAVIGATING"
        # Instant teleportation for mock
        await asyncio.sleep(0.1)
        self.states[robot_id].pose = waypoint
        self.states[robot_id].nav_state = "SUCCEEDED"
        self.states[robot_id].timestamp = time.time()
        return True
        
    async def cancel(self, robot_id: str) -> None:
        if robot_id in self.states:
            self.states[robot_id].nav_state = "CANCELED"
        
    async def pause(self, robot_id: str) -> None:
        if robot_id in self.states:
            self.states[robot_id].nav_state = "IDLE"
        
    def get_state(self, robot_id: str) -> RobotPhysicalState:
        if robot_id not in self.states:
            return RobotPhysicalState(
                robot_id=robot_id, pose=(0, 0, 0), velocity=(0, 0, 0),
                nav_state="IDLE", battery=1.0, timestamp=time.time()
            )
        return self.states[robot_id]
