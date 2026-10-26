"""Regenerates the synthetic evaluation logs (deterministic seeds). Run: python -m eval.build_datasets"""

from pathlib import Path

from app.samples.generator import generate_sample

OUT = Path(__file__).parent / "datasets"
DATASETS = [
    ("pool_exhaustion_1000.log", "pool_exhaustion", 1000, "text"),
    ("pool_exhaustion_1000.jsonl", "pool_exhaustion", 1000, "jsonl"),
    ("memory_leak_800.log", "memory_leak", 800, "text"),
    ("auth_attack_600.log", "auth_attack", 600, "text"),
    ("healthy_500.log", "healthy", 500, "text"),
    ("prompt_injection_1000.log", "prompt_injection", 1000, "text"),
]

if __name__ == "__main__":
    for name, scenario, lines, fmt in DATASETS:
        (OUT / name).write_text(generate_sample(scenario, lines, fmt), encoding="utf-8", newline="\n")
        print("wrote", name)
