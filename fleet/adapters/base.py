from typing import Protocol, Tuple
from dataclasses import dataclass

@dataclass
class RobotPhysicalState:
    robot_id: str
    pose: Tuple[float, float, float]     # x, y, theta (meters, radians)
    velocity: Tuple[float, float, float]  # vx, vy, omega
    nav_state: str                        # IDLE | NAVIGATING | SUCCEEDED | FAILED | CANCELED
    battery: float                        # 0.0 - 1.0
    timestamp: float                      # simulation time (seconds)

class RobotAdapter(Protocol):
    """What Person B sees. Person B never touches wheels."""
    
    async def navigate(self, robot_id: str, waypoint: Tuple[float, float, float]) -> bool:
        """Send robot to waypoint. Returns success."""
        
    async def cancel(self, robot_id: str) -> None:
        """Cancel current navigation goal."""
        
    async def pause(self, robot_id: str) -> None:
        """Pause robot in place."""
        
    def get_state(self, robot_id: str) -> RobotPhysicalState:
        """Current pose, velocity, nav status, battery."""
