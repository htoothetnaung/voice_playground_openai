"""Accumulates streamed LLM text until safe sentence boundaries so TTS can start before the full answer is complete."""
import re


class SentenceBuffer:
    """Buffers streamed text deltas until a safe sentence boundary for lower-latency TTS."""
    ABBREVIATIONS = {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "ave",
        "blvd",
        "rd",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
        "inc",
        "ltd",
        "corp",
        "co",
        "dept",
        "vs",
        "etc",
        "approx",
        "appt",
        "e.g",
        "i.e",
        "a.m",
        "p.m",
    }

    def __init__(self, min_length: int = 10) -> None:
        """Initialize this object with the dependencies it needs for the surrounding backend workflow."""
        self.buffer = ""
        self.min_length = min_length

    def add(self, token: str) -> list[str]:
        """Append a streamed text token and return any complete sentences ready for speech."""
        self.buffer += token
        return self._extract_sentences()

    def flush(self) -> str | None:
        """Emit any buffered final transcript as a completed speech turn."""
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining or None

    def reset(self) -> None:
        """Clear buffered text without emitting a sentence."""
        self.buffer = ""

    def _extract_sentences(self) -> list[str]:
        """Find complete sentence candidates while avoiding short fragments and known abbreviations."""
        sentences: list[str] = []
        search_pos = 0
        while True:
            match = re.search(r'[.!?][\s"]', self.buffer[search_pos:])
            if not match:
                break

            boundary_pos = search_pos + match.start() + 1
            candidate = self.buffer[:boundary_pos].strip()
            if not self._is_sentence_boundary(candidate):
                search_pos = boundary_pos + 1
                continue
            if len(candidate) < self.min_length:
                break

            sentences.append(candidate)
            self.buffer = self.buffer[boundary_pos:].lstrip()
            search_pos = 0
        return sentences

    def _is_sentence_boundary(self, text: str) -> bool:
        """Decide whether a punctuation mark is a true sentence boundary rather than an abbreviation."""
        if not text:
            return False

        words = text.rstrip(".!?").rsplit(None, 1)
        if not words:
            return True

        last_word = words[-1].lower().rstrip(".")
        if last_word in self.ABBREVIATIONS:
            return False
        return True
