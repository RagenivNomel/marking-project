from enum import Enum


class State(str, Enum):
    NEW = "NEW"
    SCANNED = "SCANNED"
    IDENTIFIED = "IDENTIFIED"
    TRANSCRIBED = "TRANSCRIBED"
    GRADED = "GRADED"
    VALIDATED = "VALIDATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    RENDERED = "RENDERED"
    COMPLETE = "COMPLETE"


STATES = list(State)
NEXT = dict(zip(STATES, STATES[1:]))


def transition(current: State, target: State) -> State:
    if NEXT.get(current) != target:
        raise ValueError(f"Invalid transition: {current.value} -> {target.value}")
    return target
