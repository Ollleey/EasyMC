"""Pick the right Java runtime for a modpack.

Modded Minecraft is picky about the JDK major version: older packs need
Java 8/17, modern ones Java 21, and the newest Java 25. This module finds the
JDKs installed in the container and chooses the best match for a Minecraft
version. If a launch fails with UnsupportedClassVersionError, the server
manager uses this module to switch to the exact version the pack reported.
"""
from __future__ import annotations

import glob
import os
import re

# Minecraft class-file version N maps to Java major (N - 44):
#   52->8, 61->17, 65->21, 69->25
def java_major_from_class_version(class_version: int) -> int:
    return class_version - 44


def installed() -> dict[int, str]:
    """Map installed Java major version -> path to its ``java`` binary."""
    found: dict[int, str] = {}
    for jbin in glob.glob("/usr/lib/jvm/*/bin/java"):
        parent = os.path.basename(os.path.dirname(os.path.dirname(jbin)))
        m = re.search(r"-(\d+)", parent)      # e.g. temurin-21-jdk-amd64 -> 21
        if m:
            found.setdefault(int(m.group(1)), jbin)
    return found


def required_for_mc(mc_version: str) -> int:
    """Best-effort Java major for a Minecraft version (a first guess)."""
    try:
        parts = [int(x) for x in mc_version.split(".")[:3]]
    except (ValueError, AttributeError):
        return 21
    while len(parts) < 3:
        parts.append(0)
    _, minor, patch = parts[0], parts[1], parts[2]
    if minor <= 16:
        return 8
    if minor <= 19:
        return 17                      # 1.17 – 1.19
    if minor == 20:
        return 21 if patch >= 5 else 17  # 1.20.5+ needs 21
    if minor == 21:
        return 21
    return 25                          # 1.22+ / newest -> assume Java 25


def pick(desired_major: int, avail: dict[int, str] | None = None) -> tuple[str, bool]:
    """Return (java_binary, exact_match). Falls back to the closest JDK.

    exact_match is False when the desired major isn't installed, so the caller
    can warn the user which JDK to add.
    """
    avail = installed() if avail is None else avail
    if not avail:
        return "java", False
    if desired_major in avail:
        return avail[desired_major], True
    higher = sorted(m for m in avail if m >= desired_major)
    if higher:
        return avail[higher[0]], False
    return avail[max(avail)], False
