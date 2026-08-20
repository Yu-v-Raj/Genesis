"""Capabilities exposed by deterministic Genesis tools."""

from enum import StrEnum


class ToolCapability(StrEnum):
    """A declarative capability supported by a Tool."""

    ECHO = "echo"
    CALCULATION = "calculation"
    IDENTIFIER_GENERATION = "identifier_generation"
    RANDOM_NUMBER = "random_number"
    DELAY = "delay"
