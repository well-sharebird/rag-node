"""
Stage 1.5 - Text Preprocessing and Cleaning
质量评分、SimHash 去重、PII 脱敏、语言检测、噪音过滤
"""
import re
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field

logger = logging.getLogger("app.preprocessing")


@dataclass
class CleaningResult:
    """Result of text cleaning pipeline"""
    text: str
    quality_score: float
    language: str
    is_duplicate: bool
    pii_detected: bool
    cleaned_text: str
    simhash: Optional[int] = None
    pii_types: Dict[str, int] = field(default_factory=dict)


class TextCleaner:
    """Text preprocessing and cleaning pipeline"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.min_text_ratio = self.config.get("min_text_ratio", 0.3)
        self.simhash_bits = self.config.get("simhash_bits", 64)
        self.enable_pii_removal = self.config.get("enable_pii_removal", True)
        self.enable_dedup = self.config.get("enable_dedup", True)
        self.quality_threshold = self.config.get("quality_threshold", 0.2)
        self._existing_hashes: Set[int] = set()

        # PII patterns - enhanced with Chinese-specific patterns
        self.pii_patterns = {
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "phone": r"\b(?:\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b",
            "phone_cn": r"\b1[3-9]\d{9}\b",  # Chinese mobile
            "id_card_cn": r"\b\d{17}[\dXx]\b",  # Chinese ID
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b\d{4}[-.]?\d{4}[-.]?\d{4}[-.]?\d{4}\b",
            "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            "passport": r"\b[A-Z]{1,2}\d{6,9}\b",
        }

        # Noise patterns
        self.noise_patterns = [
            r"\bhttps?://\S+\b",  # URLs
            r"\bwww\.\S+\b",  # WWW links
            r"@\w+",  # Mentions
            r"#\w+",  # Hashtags
            r"\b[A-Z]{2,}\b",  # All caps words
            r"[^\w\s.,!?;:()\"'-]",  # Special characters
        ]

    def calculate_quality_score(self, text: str, html: Optional[str] = None) -> float:
        """
        Calculate text quality score (0-1)
        Based on text density, punctuation, and content ratio
        """
        if not text:
            return 0.0

        score = 1.0

        # Text length penalty
        if len(text) < 100:
            score *= 0.5
        elif len(text) < 500:
            score *= 0.8

        # Text density (if HTML provided)
        if html:
            text_ratio = len(text) / max(len(html), 1)
            if text_ratio < self.min_text_ratio:
                score *= text_ratio / self.min_text_ratio

        # Punctuation ratio
        punctuation_count = sum(1 for c in text if c in ".,!?;:。！？；：")
        punctuation_ratio = punctuation_count / max(len(text), 1)
        if punctuation_ratio < 0.01:
            score *= 0.7
        elif punctuation_ratio > 0.2:
            score *= 0.8

        # Stopwords presence (English + Chinese)
        stopwords_en = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being"}
        stopwords_zh = {"的", "了", "是", "在", "和", "与", "或", "就", "都", "而", "及", "到", "着"}
        words = text.lower().split()
        stopwords_count = sum(1 for w in words if w in stopwords_en or w in stopwords_zh)
        stopwords_ratio = stopwords_count / max(len(words), 1)
        if stopwords_ratio < 0.05:
            score *= 0.8

        return max(0.0, min(1.0, score))

    def compute_simhash(self, text: str) -> int:
        """
        Compute SimHash fingerprint for deduplication
        Returns 64-bit hash
        """
        # Tokenize - split on whitespace and punctuation for better Chinese support
        tokens = re.findall(r"[\w]+", text.lower())

        # Create hash vector
        v = [0] * self.simhash_bits

        for token in tokens:
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            for i in range(self.simhash_bits):
                if h & (1 << i):
                    v[i] += 1
                else:
                    v[i] -= 1

        # Convert to fingerprint
        fingerprint = 0
        for i in range(self.simhash_bits):
            if v[i] > 0:
                fingerprint |= (1 << i)

        return fingerprint

    def hamming_distance(self, h1: int, h2: int) -> int:
        """Calculate Hamming distance between two hashes"""
        return bin(h1 ^ h2).count("1")

    def is_duplicate(self, text: str, existing_hashes: List[int], threshold: int = 3) -> bool:
        """
        Check if text is duplicate using SimHash
        threshold: max Hamming distance to consider as duplicate
        """
        if not self.enable_dedup or not existing_hashes:
            return False

        new_hash = self.compute_simhash(text)

        for existing_hash in existing_hashes:
            if self.hamming_distance(new_hash, existing_hash) <= threshold:
                return True

        return False

    def detect_and_remove_pii(self, text: str) -> Tuple[str, Dict[str, int]]:
        """
        Detect and remove PII (Personally Identifiable Information)
        Returns cleaned text and count of detected PII types
        """
        if not self.enable_pii_removal:
            return text, {}

        pii_counts = {}
        cleaned = text

        for pii_type, pattern in self.pii_patterns.items():
            matches = re.findall(pattern, cleaned, re.IGNORECASE)
            if matches:
                pii_counts[pii_type] = len(matches)
                cleaned = re.sub(pattern, f"[{pii_type.upper()}]", cleaned)

        return cleaned, pii_counts

    def detect_language(self, text: str) -> str:
        """
        Language detection using langdetect library with regex fallback
        Returns ISO language code
        """
        if not text or len(text.strip()) < 10:
            return "unknown"

        # Fast path: use langdetect for accurate detection
        try:
            from langdetect import detect, DetectorFactory
            DetectorFactory.seed = 42
            lang = detect(text[:1000])
            return lang if lang else "unknown"
        except ImportError:
            logger.debug("langdetect not installed, using regex fallback")
        except Exception:
            pass

        # Regex fallback
        cjk_pattern = re.compile(r"[一-鿿぀-ゟ゠-ヿ]")
        if cjk_pattern.search(text):
            # Check for Japanese hiragana/katakana
            if re.search(r"[぀-ゟ]", text):
                return "ja"
            elif re.search(r"[゠-ヿ]", text):
                return "ja"
            elif re.search(r"[가-힯]", text):
                return "ko"
            else:
                return "zh"

        if re.search(r"[؀-ۿ]", text):
            return "ar"

        if re.search(r"[Ѐ-ӿ]", text):
            return "ru"

        return "en"

    def remove_noise(self, text: str) -> str:
        """Remove common noise patterns"""
        cleaned = text

        for pattern in self.noise_patterns:
            cleaned = re.sub(pattern, " ", cleaned)

        # Normalize whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    def detect_encoding(self, content: bytes) -> str:
        """
        Detect encoding of raw bytes using chardet
        Returns encoding string
        """
        try:
            import chardet
            result = chardet.detect(content)
            encoding = result.get("encoding", "utf-8")
            confidence = result.get("confidence", 0.5)
            if confidence < 0.5:
                logger.warning("Low encoding confidence: %s (%.2f)", encoding, confidence)
            return encoding if encoding else "utf-8"
        except ImportError:
            logger.debug("chardet not installed, using utf-8 fallback")
            return "utf-8"

    def clean(self, text: str, html: Optional[str] = None, existing_hashes: Optional[List[int]] = None) -> CleaningResult:
        """
        Run full cleaning pipeline

        Args:
            text: Input text
            html: Optional original HTML for quality calculation
            existing_hashes: Optional list of existing simhashes for deduplication

        Returns:
            CleaningResult with cleaned text and metadata
        """
        # Calculate quality score
        quality_score = self.calculate_quality_score(text, html)

        # Detect language
        language = self.detect_language(text)

        # Compute simhash
        simhash = self.compute_simhash(text)

        # Check for duplicates
        is_dup = False
        if existing_hashes:
            is_dup = self.is_duplicate(text, existing_hashes)

        # Remove noise
        cleaned = self.remove_noise(text)

        # Detect and remove PII
        cleaned, pii_counts = self.detect_and_remove_pii(cleaned)

        return CleaningResult(
            text=text,
            quality_score=quality_score,
            language=language,
            is_duplicate=is_dup,
            pii_detected=bool(pii_counts),
            cleaned_text=cleaned,
            simhash=simhash,
            pii_types=pii_counts
        )


# Global instance
_text_cleaner: Optional[TextCleaner] = None


def get_text_cleaner(config: Optional[Dict[str, Any]] = None) -> TextCleaner:
    """Get or create text cleaner instance"""
    global _text_cleaner
    if _text_cleaner is None:
        _text_cleaner = TextCleaner(config)
    return _text_cleaner


def reset_text_cleaner():
    """Reset the global text cleaner instance"""
    global _text_cleaner
    _text_cleaner = None
