"""Tests for retrieval_contract — SegmentRecord, RetrievalRequest, RetrievalTrace."""


from packages.pipeline_services.retrieval_contract import (
    RetrievalRequest,
    RetrievalTrace,
    SegmentRecord,
)


class TestSegmentRecord:
    def test_minimal_construction(self) -> None:
        seg = SegmentRecord(
            segment_id="seg-001",
            text="充分烹熟后食用荔枝菌。",
            tags=["荔枝菌", "安全"],
        )
        assert seg.segment_id == "seg-001"
        assert seg.text == "充分烹熟后食用荔枝菌。"
        assert seg.tags == ["荔枝菌", "安全"]
        assert seg.brand_id == ""
        assert seg.category_id == ""
        assert seg.product_id == ""
        assert seg.source_id == ""
        assert seg.source_type == ""
        assert seg.normalized_text == ""
        assert seg.claims == []
        assert seg.risk_flags == []
        assert seg.created_at == ""

    def test_full_construction(self) -> None:
        seg = SegmentRecord(
            segment_id="seg-002",
            brand_id="brand-ziyuantang",
            category_id="cat-mushroom",
            product_id="prod-jianshouqing",
            source_id="src-001",
            source_type="video",
            text="滋元堂提醒您注意饮食健康。",
            normalized_text="滋元堂提醒您注意饮食健康",
            tags=["品牌", "健康"],
            claims=["安全食用", "高品质"],
            risk_flags=["未充分烹熟"],
            created_at="2025-05-18T10:00:00Z",
        )
        assert seg.segment_id == "seg-002"
        assert seg.brand_id == "brand-ziyuantang"
        assert seg.category_id == "cat-mushroom"
        assert seg.product_id == "prod-jianshouqing"
        assert seg.source_id == "src-001"
        assert seg.source_type == "video"
        assert seg.normalized_text == "滋元堂提醒您注意饮食健康"
        assert seg.claims == ["安全食用", "高品质"]
        assert seg.risk_flags == ["未充分烹熟"]
        assert seg.created_at == "2025-05-18T10:00:00Z"

    def test_serialization_roundtrip(self) -> None:
        seg = SegmentRecord(
            segment_id="seg-003",
            text="测试文本",
            tags=["标签1"],
            claims=["声明A"],
            risk_flags=["风险X"],
        )
        data = seg.model_dump()
        restored = SegmentRecord(**data)
        assert restored == seg

    def test_json_roundtrip(self) -> None:
        seg = SegmentRecord(
            segment_id="seg-004",
            text="JSON 测试",
            tags=["x"],
            created_at="2025-01-01T00:00:00Z",
        )
        payload = seg.model_dump_json()
        restored = SegmentRecord.model_validate_json(payload)
        assert restored == seg


class TestRetrievalRequest:
    def test_defaults(self) -> None:
        req = RetrievalRequest(query="荔枝菌怎么吃")
        assert req.query == "荔枝菌怎么吃"
        assert req.top_k == 10
        assert req.request_id == ""
        assert req.project_id == ""
        assert req.job_id == ""
        assert req.task_id == ""
        assert req.brand_id == ""
        assert req.category_id == ""
        assert req.product_id == ""
        assert req.query_type == ""
        assert req.filters == {}
        assert req.risk_policy == {}
        assert req.created_at == ""

    def test_with_filters_and_policy(self) -> None:
        req = RetrievalRequest(
            query="羊肚菌",
            top_k=5,
            project_id="002羊肚菌",
            query_type="keyword",
            filters={"project": "002羊肚菌", "min_duration": 5.0},
            risk_policy={"max_risk_level": "medium"},
        )
        assert req.top_k == 5
        assert req.query_type == "keyword"
        assert req.filters == {"project": "002羊肚菌", "min_duration": 5.0}
        assert req.risk_policy == {"max_risk_level": "medium"}

    def test_roundtrip(self) -> None:
        req = RetrievalRequest(
            request_id="req-001",
            query="test",
            top_k=3,
            risk_policy={"block_claims": ["医疗功效"]},
        )
        restored = RetrievalRequest.model_validate_json(req.model_dump_json())
        assert restored == req


class TestRetrievalTrace:
    def test_minimal_construction(self) -> None:
        trace = RetrievalTrace(
            request_id="req-001",
        )
        assert trace.request_id == "req-001"
        assert trace.operator_decision == "approved"
        assert trace.auto_filters_applied == []
        assert trace.manual_overrides == []
        assert trace.risk_review == {}
        assert trace.final_context_segment_ids == []
        assert trace.created_at == ""
        assert trace.updated_at == ""

    def test_with_decision_and_overrides(self) -> None:
        trace = RetrievalTrace(
            request_id="req-002",
            operator_decision="edited",
            auto_filters_applied=["no_medical_claims"],
            manual_overrides=[
                {"field": "text", "old": "...", "new": "..."},
            ],
            risk_review={"passed": True, "flags": 0},
            final_context_segment_ids=["seg-001", "seg-003"],
            created_at="2025-05-18T10:00:00Z",
            updated_at="2025-05-18T10:05:00Z",
        )
        assert trace.request_id == "req-002"
        assert trace.operator_decision == "edited"
        assert trace.auto_filters_applied == ["no_medical_claims"]
        assert trace.manual_overrides == [
            {"field": "text", "old": "...", "new": "..."},
        ]
        assert trace.risk_review == {"passed": True, "flags": 0}
        assert trace.final_context_segment_ids == ["seg-001", "seg-003"]
        assert trace.updated_at == "2025-05-18T10:05:00Z"

    def test_operator_decision_values(self) -> None:
        from typing import get_args
        from packages.pipeline_services.retrieval_contract import RetrievalTrace
        Decision = get_args(RetrievalTrace.model_fields["operator_decision"].annotation)
        for decision in Decision:
            trace = RetrievalTrace(request_id="r", operator_decision=decision)
            assert trace.operator_decision == decision

    def test_roundtrip(self) -> None:
        trace = RetrievalTrace(
            request_id="req-roundtrip",
            operator_decision="needs_more_evidence",
            auto_filters_applied=["f1"],
            manual_overrides=[{"k": "v"}],
            risk_review={"score": 0.5},
            final_context_segment_ids=["s1"],
        )
        restored = RetrievalTrace.model_validate_json(trace.model_dump_json())
        assert restored == trace
