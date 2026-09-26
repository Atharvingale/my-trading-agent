"""Candidate Research & Evolution plane (Module 15).

Research-only: candidates may exist without PASS. Nothing here can wire a
production strategy on its own. Promotion still needs Module 1 PASS plus
explicit human approval plus an immutable production version (see Module 4).
"""

from candidate_generation.generator import CandidateGenerator, CandidateHypothesis
from candidate_generation.hypothesis_menu import HypothesisMenu
from candidate_generation import multiple_testing
from candidate_generation.provider_client import propose_hypothesis
from candidate_generation.review_queue import ReviewQueue

__all__ = [
    "CandidateGenerator",
    "CandidateHypothesis",
    "HypothesisMenu",
    "multiple_testing",
    "propose_hypothesis",
    "ReviewQueue",
]
