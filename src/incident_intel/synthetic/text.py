"""Helpers that make generated text look like it came from real people."""

import random

from incident_intel.domain import TicketChannel

FIRST_NAMES = [
    "maria", "james", "aisha", "wei", "carlos", "priya", "liam", "fatima", "kenji", "olga",
    "noah", "zara", "diego", "mei", "arjun", "sofia", "tom", "amara", "lucas", "hana",
]  # fmt: skip
LAST_NAMES = [
    "chen", "smith", "khan", "garcia", "patel", "nguyen", "okafor", "kim", "rossi", "silva",
    "mueller", "haddad", "ivanova", "tanaka", "brown", "singh", "lopez", "novak", "adeyemi",
]  # fmt: skip

HARMLESS_CHANGES = [
    "Update dependency versions",
    "Add debug logging to {resource} handler",
    "Tune cache TTL for {resource}",
    "Copy change on product page",
    "Remove unused feature flag",
    "Bump base Docker image",
    "Add metrics for {resource} endpoint",
]

RISKY_CHANGES = [
    "Refactor request validation",
    "Migrate to new JSON serialization library",
    "Rewrite {resource} pagination",
    "Change default timeout handling",
    "Upgrade ORM to new major version",
]


def random_employee(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)}.{rng.choice(LAST_NAMES)}@shopfast.example"


def random_reporter(rng: random.Random) -> str:
    """Tickets come from employees (40%) and customers (60%)."""
    if rng.random() < 0.4:
        return random_employee(rng)
    return f"customer-{rng.randint(10000, 99999)}"


def random_channel(rng: random.Random) -> TicketChannel:
    channels = [TicketChannel.PORTAL, TicketChannel.EMAIL, TicketChannel.CHAT, TicketChannel.PHONE]
    return rng.choices(channels, weights=[4, 3, 2, 1])[0]


def humanize(text: str, rng: random.Random) -> str:
    """Make template text look typed by a busy human: casing, punctuation, typos.

    Real tickets are messy, and a classifier trained only on tidy text breaks on
    real input. A little noise keeps the later ML steps honest.
    """
    if rng.random() < 0.3:
        text = text.lower()
    if rng.random() < 0.2:
        text = text.rstrip(".!?")
    if rng.random() < 0.15:
        text += rng.choice([" pls help", " urgent!!", " asap", "??"])
    if rng.random() < 0.2:
        text = _add_typo(text, rng)
    return text


def _add_typo(text: str, rng: random.Random) -> str:
    """Swap two neighbouring letters in one longer word ("checkout" -> "chekcout")."""
    words = text.split(" ")
    candidates = [i for i, word in enumerate(words) if len(word) > 4 and word.isalpha()]
    if not candidates:
        return text
    i = rng.choice(candidates)
    word = words[i]
    j = rng.randint(1, len(word) - 2)
    words[i] = word[:j] + word[j + 1] + word[j] + word[j + 2 :]
    return " ".join(words)
