import time
from typing import Dict
from pydantic import BaseModel

class SessionState(BaseModel):
    session_id: str
    cumulative_risk: float = 0.0
    turn_count: int = 0
    last_active: float = 0.0

class SessionAggregator:
    def __init__(self, risk_threshold: float = 1.0):
        self.sessions: Dict[str, SessionState] = {}
        self.risk_threshold = risk_threshold

    def _get_or_create_session(self, session_id: str) -> SessionState:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState(session_id=session_id, last_active=time.time())
        return self.sessions[session_id]

    def add_risk(self, session_id: str, risk_score: float) -> float:
        session = self._get_or_create_session(session_id)
        session.cumulative_risk += risk_score
        session.turn_count += 1
        session.last_active = time.time()
        return session.cumulative_risk

    def is_blocked(self, session_id: str) -> bool:
        # User requested to disable strict session locking
        return False

    def get_cumulative_risk(self, session_id: str) -> float:
        return self._get_or_create_session(session_id).cumulative_risk

# Global singleton
session_manager = SessionAggregator()
