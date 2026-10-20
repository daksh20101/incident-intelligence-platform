"""Synthetic data: a fictional company (ShopFast) with incidents we know the answers to."""

from incident_intel.synthetic.generator import generate_world
from incident_intel.synthetic.world import GeneratorConfig, World

__all__ = ["GeneratorConfig", "World", "generate_world"]
