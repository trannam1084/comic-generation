"""TV1 offline evaluation preparation; không inference, dataset discovery hoặc TV3 rubric."""

from .contracts import EvaluationInput, EvaluationPlan, HumanAnnotation, InferenceCost, PairedCaseResult
from .integrity import json_bytes, parse_record, sha256_bytes, sha256_text, verify_reference, write_session
from .semantic import annotation_readiness, blank_annotation, prepare_semantic_matches
from .structural import evaluate_pairs

__all__ = ["EvaluationInput", "EvaluationPlan", "HumanAnnotation", "InferenceCost", "PairedCaseResult", "evaluate_pairs",
           "annotation_readiness", "prepare_semantic_matches", "parse_record", "json_bytes",
           "sha256_bytes", "sha256_text", "verify_reference", "write_session", "blank_annotation"]
