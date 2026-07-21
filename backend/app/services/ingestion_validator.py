"""
Stage 5.5 - Ingestion Quality Validation
分块质量检查、Embedding 异常检测、索引回查验证、覆盖率检查、Golden 样本测试
"""
from __future__ import annotations
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("app.services.ingestion_validator")


class ValidationStatus(Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass
class ValidationFinding:
    """Single validation finding"""
    check_name: str
    status: ValidationStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    severity: int = 1  # 1=low, 2=medium, 3=high


@dataclass
class ValidationResult:
    """Overall validation result for a document"""
    document_id: str
    document_name: str
    total_chunks: int
    passed_checks: int = 0
    warning_checks: int = 0
    failed_checks: int = 0
    findings: List[ValidationFinding] = field(default_factory=list)
    overall_status: ValidationStatus = ValidationStatus.PASSED
    metrics: Dict[str, float] = field(default_factory=dict)

    def add_finding(self, finding: ValidationFinding):
        self.findings.append(finding)
        if finding.status == ValidationStatus.PASSED:
            self.passed_checks += 1
        elif finding.status == ValidationStatus.WARNING:
            self.warning_checks += 1
        else:
            self.failed_checks += 1
            # Update overall status to failed if any high severity finding
            if finding.severity >= 3:
                self.overall_status = ValidationStatus.FAILED
            elif self.overall_status == ValidationStatus.PASSED:
                self.overall_status = ValidationStatus.WARNING


class IngestionValidator:
    """
    Validates the quality of ingested documents and their chunks.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # Thresholds
        self.min_chunk_length = self.config.get("min_chunk_length", 20)
        self.max_chunk_length = self.config.get("max_chunk_length", 10000)
        self.min_embedding_norm = self.config.get("min_embedding_norm", 0.5)
        self.max_embedding_norm = self.config.get("max_embedding_norm", 1.5)
        self.max_embedding_variance = self.config.get("max_embedding_variance", 10.0)
        self.min_recall_threshold = self.config.get("min_recall_threshold", 0.7)
        self.min_coverage_ratio = self.config.get("min_coverage_ratio", 0.95)
        self.empty_chunk_ratio_threshold = self.config.get("empty_chunk_ratio_threshold", 0.1)

    def validate_chunks(
        self,
        chunks: List[Any],
        original_text: str,
    ) -> List[ValidationFinding]:
        """
        Validate chunk quality.

        Checks:
        - Empty or very short chunks
        - Extremely long chunks
        - Chunk count vs original text length
        - Coverage ratio (chunked text vs original)
        """
        findings = []

        if not chunks:
            findings.append(ValidationFinding(
                check_name="chunk_count",
                status=ValidationStatus.FAILED,
                message="No chunks generated",
                severity=3,
            ))
            return findings

        # Check for empty/short chunks
        empty_count = 0
        short_chunks = []
        long_chunks = []

        for i, chunk in enumerate(chunks):
            text = chunk.text if hasattr(chunk, "text") else str(chunk)
            if not text.strip():
                empty_count += 1
            elif len(text) < self.min_chunk_length:
                short_chunks.append((i, len(text)))
            elif len(text) > self.max_chunk_length:
                long_chunks.append((i, len(text)))

        # Report empty chunks
        empty_ratio = empty_count / len(chunks)
        if empty_ratio > self.empty_chunk_ratio_threshold:
            findings.append(ValidationFinding(
                check_name="empty_chunks",
                status=ValidationStatus.FAILED,
                message=f"{empty_count}/{len(chunks)} chunks are empty ({empty_ratio:.1%})",
                details={"empty_count": empty_count, "ratio": empty_ratio},
                severity=3,
            ))
        elif empty_count > 0:
            findings.append(ValidationFinding(
                check_name="empty_chunks",
                status=ValidationStatus.WARNING,
                message=f"{empty_count} empty chunks detected",
                details={"empty_count": empty_count},
                severity=1,
            ))

        # Report short chunks
        if short_chunks:
            findings.append(ValidationFinding(
                check_name="short_chunks",
                status=ValidationStatus.WARNING,
                message=f"{len(short_chunks)} chunks below min length ({self.min_chunk_length} chars)",
                details={"short_chunks": short_chunks[:10]},  # First 10
                severity=1,
            ))

        # Report long chunks
        if long_chunks:
            findings.append(ValidationFinding(
                check_name="long_chunks",
                status=ValidationStatus.WARNING,
                message=f"{len(long_chunks)} chunks exceed max length ({self.max_chunk_length} chars)",
                details={"long_chunks": long_chunks[:10]},
                severity=2,
            ))

        # Coverage check - compare chunked text vs original
        chunked_text = "".join(
            c.text if hasattr(c, "text") else str(c)
            for c in chunks
        )
        coverage_ratio = len(chunked_text) / max(len(original_text), 1)
        if coverage_ratio < self.min_coverage_ratio:
            findings.append(ValidationFinding(
                check_name="coverage_ratio",
                status=ValidationStatus.WARNING,
                message=f"Low coverage: {coverage_ratio:.1%} of original text",
                details={"coverage_ratio": coverage_ratio, "threshold": self.min_coverage_ratio},
                severity=2,
            ))
        else:
            findings.append(ValidationFinding(
                check_name="coverage_ratio",
                status=ValidationStatus.PASSED,
                message=f"Coverage: {coverage_ratio:.1%}",
                details={"coverage_ratio": coverage_ratio},
            ))

        return findings

    def validate_embeddings(
        self,
        embeddings: List[List[float]],
        chunk_texts: List[str],
    ) -> List[ValidationFinding]:
        """
        Validate embedding quality.

        Checks:
        - Zero or near-zero vectors
        - Abnormal vector norms
        - High variance in embeddings
        - Dimension consistency
        """
        findings = []

        if not embeddings:
            findings.append(ValidationFinding(
                check_name="embedding_count",
                status=ValidationStatus.FAILED,
                message="No embeddings generated",
                severity=3,
            ))
            return findings

        # Check dimensions consistency
        dims = [len(e) for e in embeddings]
        if len(set(dims)) > 1:
            findings.append(ValidationFinding(
                check_name="dimension_consistency",
                status=ValidationStatus.FAILED,
                message=f"Inconsistent embedding dimensions: {set(dims)}",
                details={"dimensions": list(set(dims))},
                severity=3,
            ))
            return findings

        expected_dim = dims[0]

        # Check for zero/near-zero vectors
        zero_vectors = 0
        norms = []

        for i, emb in enumerate(embeddings):
            norm = np.linalg.norm(emb)
            norms.append(norm)
            if norm < self.min_embedding_norm:
                zero_vectors += 1

        if zero_vectors > 0:
            findings.append(ValidationFinding(
                check_name="zero_vectors",
                status=ValidationStatus.FAILED,
                message=f"{zero_vectors} embeddings have near-zero norm",
                details={"zero_count": zero_vectors, "threshold": self.min_embedding_norm},
                severity=3,
            ))

        # Check norm range
        min_norm = min(norms)
        max_norm = max(norms)
        if min_norm < self.min_embedding_norm or max_norm > self.max_embedding_norm:
            findings.append(ValidationFinding(
                check_name="embedding_norm",
                status=ValidationStatus.WARNING,
                message=f"Embedding norms out of range: [{min_norm:.3f}, {max_norm:.3f}]",
                details={"min_norm": min_norm, "max_norm": max_norm},
                severity=2,
            ))
        else:
            findings.append(ValidationFinding(
                check_name="embedding_norm",
                status=ValidationStatus.PASSED,
                message=f"Embedding norms in range: [{min_norm:.3f}, {max_norm:.3f}]",
                details={"min_norm": min_norm, "max_norm": max_norm, "mean_norm": np.mean(norms)},
            ))

        # Check variance
        embeddings_array = np.array(embeddings)
        variance = np.var(embeddings_array)
        if variance > self.max_embedding_variance:
            findings.append(ValidationFinding(
                check_name="embedding_variance",
                status=ValidationStatus.WARNING,
                message=f"High embedding variance: {variance:.4f}",
                details={"variance": float(variance)},
                severity=2,
            ))
        else:
            findings.append(ValidationFinding(
                check_name="embedding_variance",
                status=ValidationStatus.PASSED,
                message=f"Embedding variance: {variance:.4f}",
                details={"variance": float(variance)},
            ))

        return findings

    async def validate_index_recall(
        self,
        milvus_client,
        collection_name: str,
        chunk_texts: List[str],
        embeddings: List[List[float]],
        doc_id: str,
    ) -> ValidationFinding:
        """
        Validate index recall by querying with chunk's own embedding.
        A chunk should retrieve itself with high similarity.
        """
        if not chunk_texts or not embeddings:
            return ValidationFinding(
                check_name="index_recall",
                status=ValidationStatus.FAILED,
                message="No chunks or embeddings to validate",
                severity=3,
            )

        # Sample up to 10 chunks for recall check
        sample_size = min(10, len(chunk_texts))
        sample_indices = np.random.choice(len(chunk_texts), sample_size, replace=False)

        recall_successes = 0
        recall_failures = []

        for idx in sample_indices:
            try:
                query_emb = [embeddings[idx]]
                chunk_text = chunk_texts[idx]

                # Search in Milvus
                results = milvus_client.search(
                    collection_name=collection_name,
                    data=query_emb,
                    limit=5,
                    filter=f'doc_id == "{doc_id}"',
                )

                # Check if the chunk retrieves itself (or a very similar chunk)
                # We check if any result has high similarity with the query
                if results and len(results[0]) > 0:
                    top_hit = results[0][0]
                    if top_hit.score >= 0.9:  # High similarity threshold
                        recall_successes += 1
                    else:
                        recall_failures.append({
                            "chunk_idx": idx,
                            "top_score": top_hit.score,
                        })
                else:
                    recall_failures.append({
                        "chunk_idx": idx,
                        "error": "no results",
                    })

            except Exception as e:
                recall_failures.append({
                    "chunk_idx": idx,
                    "error": str(e),
                })

        recall_rate = recall_successes / sample_size
        if recall_rate >= self.min_recall_threshold:
            return ValidationFinding(
                check_name="index_recall",
                status=ValidationStatus.PASSED,
                message=f"Index recall@1: {recall_rate:.1%}",
                details={"recall_rate": recall_rate, "sample_size": sample_size},
            )
        else:
            return ValidationFinding(
                check_name="index_recall",
                status=ValidationStatus.FAILED,
                message=f"Low index recall@1: {recall_rate:.1%}",
                details={"recall_rate": recall_rate, "failures": recall_failures[:5]},
                severity=3,
            )

    def validate_against_golden(
        self,
        chunk_texts: List[str],
        golden_queries: List[Dict[str, Any]],
        retrieval_fn,
    ) -> List[ValidationFinding]:
        """
        Validate ingestion against golden test queries.

        Args:
            chunk_texts: List of chunk texts
            golden_queries: List of {query: str, expected_chunk_ids: List[str]}
            retrieval_fn: Function to call for retrieval (query) -> List[chunk_id]

        Returns:
            List of validation findings
        """
        findings = []

        if not golden_queries:
            return findings

        passed = 0
        failed = 0

        for golden in golden_queries:
            query = golden.get("query", "")
            expected_ids = set(golden.get("expected_chunk_ids", []))

            if not query or not expected_ids:
                continue

            try:
                # Perform retrieval
                retrieved_ids = set(retrieval_fn(query))

                # Check if expected chunks are retrieved
                if expected_ids & retrieved_ids:
                    passed += 1
                else:
                    failed += 1
                    findings.append(ValidationFinding(
                        check_name="golden_query",
                        status=ValidationStatus.WARNING,
                        message=f"Golden query failed: {query[:50]}...",
                        details={"query": query, "expected": list(expected_ids)[:5]},
                        severity=2,
                    ))
            except Exception as e:
                failed += 1
                findings.append(ValidationFinding(
                    check_name="golden_query",
                    status=ValidationStatus.FAILED,
                    message=f"Golden query error: {e}",
                    details={"query": query, "error": str(e)},
                    severity=2,
                ))

        total = passed + failed
        if total > 0:
            pass_rate = passed / total
            findings.append(ValidationFinding(
                check_name="golden_tests",
                status=ValidationStatus.PASSED if pass_rate >= 0.8 else ValidationStatus.FAILED,
                message=f"Golden tests: {passed}/{total} passed ({pass_rate:.1%})",
                details={"passed": passed, "failed": failed, "pass_rate": pass_rate},
                severity=3 if failed > 0 else 1,
            ))

        return findings

    def validate_document(
        self,
        doc_id: str,
        doc_name: str,
        chunks: List[Any],
        embeddings: List[List[float]],
        original_text: str,
    ) -> ValidationResult:
        """
        Run full validation suite on a document.
        """
        result = ValidationResult(
            document_id=doc_id,
            document_name=doc_name,
            total_chunks=len(chunks),
        )

        # Chunk validation
        chunk_findings = self.validate_chunks(chunks, original_text)
        for f in chunk_findings:
            result.add_finding(f)

        # Embedding validation
        chunk_texts = [c.text if hasattr(c, "text") else str(c) for c in chunks]
        emb_findings = self.validate_embeddings(embeddings, chunk_texts)
        for f in emb_findings:
            result.add_finding(f)

        # Add metrics
        result.metrics = {
            "chunk_count": len(chunks),
            "avg_chunk_length": np.mean([len(t) for t in chunk_texts]) if chunk_texts else 0,
            "avg_embedding_norm": np.mean([np.linalg.norm(e) for e in embeddings]) if embeddings else 0,
            "embedding_variance": float(np.var(np.array(embeddings))) if embeddings else 0,
        }

        return result


# Global instance
_validator: Optional[IngestionValidator] = None


def get_ingestion_validator(config: Optional[Dict[str, Any]] = None) -> IngestionValidator:
    """Get or create ingestion validator instance"""
    global _validator
    if _validator is None:
        _validator = IngestionValidator(config)
    return _validator


def reset_ingestion_validator():
    """Reset the global validator instance"""
    global _validator
    _validator = None
