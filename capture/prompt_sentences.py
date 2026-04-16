"""
Capture prompt sentences for InkClone handwriting data collection.
Designed to cover all 26 lowercase letters with 3+ occurrences each,
plus uppercase, digits, and common punctuation.
"""

CAPTURE_SENTENCES = [
    "the quick brown fox jumped over the lazy dog while the gentle breeze swept through the evening air",
    "Dr. James K. Blackwell from New York City asked, 'Why don't we visit Quebec and Zimbabwe next August?'",
    "On July 4, 1776, exactly 56 men signed it; by 1790 (14 years later) the population was 3,928,214.",
    "She just explained that the situation was quite complicated, and that nothing would change everything, but working hard enough can bring some truly surprising results over time.",
    "The freezing wind blew six heavy packages across the vast empty parking lot while Jasmine joyfully and quickly photographed the whole extraordinary scene.",
]


def analyze_coverage():
    """Analyze character coverage across all capture sentences.

    Returns dict with:
      - lowercase_count: dict of char -> count for a-z
      - uppercase_count: dict of char -> count for A-Z
      - digit_count: dict of char -> count for 0-9
      - punctuation_count: dict of char -> count for non-alnum non-space
      - missing_lowercase: list of chars with 0 occurrences
      - low_coverage_lowercase: list of (char, count) with count < 3
      - total_chars: total character count across all sentences
    """
    import string
    from collections import Counter

    all_text = " ".join(CAPTURE_SENTENCES)

    counter = Counter(all_text)

    lowercase_count = {c: counter.get(c, 0) for c in string.ascii_lowercase}
    uppercase_count = {c: counter.get(c, 0) for c in string.ascii_uppercase}
    digit_count = {c: counter.get(c, 0) for c in string.digits}
    punctuation_count = {
        c: count
        for c, count in counter.items()
        if not c.isalnum() and not c.isspace()
    }

    missing_lowercase = [c for c, n in lowercase_count.items() if n == 0]
    low_coverage_lowercase = [(c, n) for c, n in lowercase_count.items() if 0 < n < 3]

    total_chars = sum(counter.values())

    # --- print report ---
    print("=" * 60)
    print("CAPTURE SENTENCE COVERAGE REPORT")
    print("=" * 60)
    print(f"Total characters (incl. spaces): {total_chars}")
    print(f"Total sentences: {len(CAPTURE_SENTENCES)}")
    print()

    print("LOWERCASE LETTER FREQUENCY TABLE:")
    print("-" * 40)
    cols = 6
    items = sorted(lowercase_count.items())
    for i in range(0, len(items), cols):
        row = items[i : i + cols]
        print("  " + "  ".join(f"{c}: {n:3d}" for c, n in row))
    print()

    covered = sum(1 for n in lowercase_count.values() if n > 0)
    print(f"Lowercase coverage: {covered}/26 letters present")
    sufficient = sum(1 for n in lowercase_count.values() if n >= 3)
    print(f"Lowercase 3+ occurrences: {sufficient}/26")

    if missing_lowercase:
        print(f"MISSING lowercase: {', '.join(missing_lowercase)}")
    if low_coverage_lowercase:
        print(f"LOW coverage (<3) lowercase: {', '.join(f'{c}({n})' for c,n in low_coverage_lowercase)}")
    if not missing_lowercase and not low_coverage_lowercase:
        print("All 26 lowercase letters have 3+ occurrences. PASS")
    print()

    print("UPPERCASE letters present:")
    up_present = sorted(c for c, n in uppercase_count.items() if n > 0)
    print(f"  {' '.join(up_present)} ({len(up_present)}/26)")
    print()

    print("DIGITS present:")
    dig_present = sorted(c for c, n in digit_count.items() if n > 0)
    print(f"  {' '.join(dig_present)} ({len(dig_present)}/10)")
    print()

    print("PUNCTUATION present:")
    for c, n in sorted(punctuation_count.items(), key=lambda x: -x[1]):
        print(f"  '{c}': {n}")
    print()

    return {
        "lowercase_count": lowercase_count,
        "uppercase_count": uppercase_count,
        "digit_count": digit_count,
        "punctuation_count": punctuation_count,
        "missing_lowercase": missing_lowercase,
        "low_coverage_lowercase": low_coverage_lowercase,
        "total_chars": total_chars,
        "lowercase_covered": covered,
        "lowercase_sufficient": sufficient,
    }


if __name__ == "__main__":
    stats = analyze_coverage()
    if stats["missing_lowercase"] or stats["low_coverage_lowercase"]:
        print("ACTION REQUIRED: Some lowercase letters need more coverage.")
        import sys
        sys.exit(1)
    else:
        print("Coverage check PASSED.")
