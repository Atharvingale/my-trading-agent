"""Trade intelligence and continuous learning (Module 9).

Diagnoses closed trades with fixed rules, banks candidate lessons, and routes
any strategy change through the Module 1 gate before production — never
directly. A single loss never mutates live parameters. No LLM calls here.
"""

from learning.lesson_engine import LessonEngine
from learning.trade_analyzer import analyze_trade

__all__ = ["LessonEngine", "analyze_trade"]
