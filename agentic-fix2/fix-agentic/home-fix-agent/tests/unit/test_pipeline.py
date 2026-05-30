"""Unit tests for the home fix agent."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models.schemas import (
    ChatMessage, ChatRole, IssueAnalysis, OrderRecord, OrderStatus,
    PipelineResult, PipelineStage, ProductResult, ProductSpec,
    Session, SessionStatus,
)
from src.agents.product_ranker import rank, _normalize
from src.agents.order_manager import create_order, confirm_order, cancel_order
from src.intake.photo import validate_and_store, ALLOWED_EXTENSIONS

FIXTURES = Path(__file__).parent.parent / "fixtures"


# --- Schema tests ---

class TestSchemas:
    def test_session_defaults(self):
        s = Session()
        assert s.session_id
        assert s.status == SessionStatus.ACTIVE

    def test_issue_analysis(self):
        a = IssueAnalysis(item_category="bulb", problem_type="burned_out", confidence=0.9)
        assert a.analysis_id
        assert a.visible_text == []
        assert a.difficulty_score == 1
        assert a.required_tools == []

    def test_issue_analysis_with_difficulty(self):
        a = IssueAnalysis(
            item_category="garage door panel", problem_type="dented",
            confidence=0.85, difficulty_score=4,
            difficulty_summary="1-2 people, half day, significant DIY skill",
            required_tools=["socket wrench", "pry bar", "level"],
        )
        assert a.difficulty_score == 4
        assert len(a.required_tools) == 3

    def test_product_spec(self):
        s = ProductSpec(item_category="bulb", attributes={"base_type": "E26"}, search_query="E26 bulb")
        assert s.spec_id
        assert s.attributes["base_type"] == "E26"

    def test_pipeline_result_defaults(self):
        r = PipelineResult(session=Session())
        assert r.analysis is None
        assert r.products == []
        assert r.stage == PipelineStage.UPLOAD
        assert r.messages == []

    def test_pipeline_stage_enum(self):
        assert PipelineStage.CLARIFYING == "clarifying"
        assert PipelineStage.RESULTS == "results"

    def test_chat_message(self):
        m = ChatMessage(role=ChatRole.ASSISTANT, content="hello")
        assert m.role == ChatRole.ASSISTANT
        assert m.timestamp is not None

    def test_pipeline_result_with_messages(self):
        r = PipelineResult(session=Session(), stage=PipelineStage.CLARIFYING)
        r.messages.append(ChatMessage(role=ChatRole.ASSISTANT, content="question?", stage="clarifying"))
        assert len(r.messages) == 1
        assert r.stage == PipelineStage.CLARIFYING

    def test_pipeline_result_serialization(self):
        r = PipelineResult(session=Session(), stage=PipelineStage.RESULTS)
        r.messages.append(ChatMessage(role=ChatRole.USER, content="test"))
        data = r.model_dump(mode="json")
        restored = PipelineResult.model_validate(data)
        assert restored.stage == PipelineStage.RESULTS
        assert len(restored.messages) == 1


# --- Photo intake tests ---

class TestPhotoIntake:
    def test_rejects_missing_file(self):
        with pytest.raises(FileNotFoundError):
            validate_and_store("/nonexistent/photo.jpg", "test_session")

    def test_rejects_bad_format(self):
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            f.write(b"fake")
            f.flush()
            with pytest.raises(ValueError, match="Unsupported format"):
                validate_and_store(f.name, "test_session")
            Path(f.name).unlink()

    def test_rejects_oversized(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"x" * (21 * 1024 * 1024))
            f.flush()
            with pytest.raises(ValueError, match="too large"):
                validate_and_store(f.name, "test_session")
            Path(f.name).unlink()

    def test_accepts_valid_jpg(self, tmp_path):
        photo = tmp_path / "test.jpg"
        photo.write_bytes(b"\xff\xd8\xff" + b"x" * 100)
        result = validate_and_store(str(photo), "test_intake")
        assert Path(result).exists()
        assert result.endswith(".jpg")


# --- Ranking tests ---

class TestRanking:
    def _make_products(self) -> list[ProductResult]:
        return [
            ProductResult(title="Philips LED A19 60W 2700K", price_cents=897, rating=4.7, review_count=12000, availability="in_stock"),
            ProductResult(title="Cheap Bulb", price_cents=199, rating=3.5, review_count=100, availability="in_stock"),
            ProductResult(title="Premium LED A19 60W 2700K Dimmable", price_cents=1299, rating=4.9, review_count=5000, availability="in_stock"),
        ]

    def test_normalize(self):
        assert _normalize([1, 2, 3]) == [0.0, 0.5, 1.0]
        assert _normalize([1, 2, 3], invert=True) == [1.0, 0.5, 0.0]
        assert _normalize([5, 5, 5]) == [1.0, 1.0, 1.0]

    def test_rank_deterministic(self):
        products = self._make_products()
        spec = ProductSpec(item_category="bulb", search_query="LED A19 60W 2700K")
        r1 = rank(products[:], spec)
        r2 = rank(products[:], spec)
        assert [p.result_id for p in r1] == [p.result_id for p in r2]

    def test_rank_spec_match_matters(self):
        products = self._make_products()
        spec = ProductSpec(item_category="bulb", search_query="LED A19 60W 2700K")
        ranked = rank(products, spec)
        assert ranked[-1].title == "Cheap Bulb"

    def test_rank_assigns_ranks(self):
        products = self._make_products()
        spec = ProductSpec(item_category="bulb", search_query="LED A19 60W 2700K")
        ranked = rank(products, spec)
        assert [p.rank for p in ranked] == [1, 2, 3]


# --- Order manager tests ---

class TestOrderManager:
    def test_create_order(self):
        p = ProductResult(title="Test Bulb", price_cents=500)
        order = create_order("sess1", p)
        assert order.status == OrderStatus.PENDING
        assert order.total_price_cents == 500

    def test_confirm_order(self):
        p = ProductResult(title="Test Bulb", price_cents=500)
        order = create_order("sess1", p)
        confirmed = confirm_order(order)
        assert confirmed.status == OrderStatus.PLACED
        assert confirmed.retailer_order_id.startswith("MOCK-")
        assert confirmed.confirmed_at is not None

    def test_cancel_order(self):
        p = ProductResult(title="Test Bulb", price_cents=500)
        order = create_order("sess1", p)
        cancelled = cancel_order(order)
        assert cancelled.status == OrderStatus.CANCELLED

    def test_quantity(self):
        p = ProductResult(title="Test Bulb", price_cents=500)
        order = create_order("sess1", p, quantity=3)
        assert order.total_price_cents == 1500


# --- Mock search tests ---

class TestMockSearch:
    def test_mock_fixture_loads(self):
        from src.agents.product_searcher import _MOCK_FILE
        data = json.loads(_MOCK_FILE.read_text())
        assert "bulb" in data
        assert len(data["bulb"]) >= 3

    def test_mock_search_returns_products(self):
        from src.agents.product_searcher import _search_mock
        results = _search_mock("LED bulb E26")
        assert len(results) >= 3
        assert all(isinstance(r, ProductResult) for r in results)


# --- Pipeline tests ---

class TestPipeline:
    def _mock_analysis(self, *args, **kwargs):
        return IssueAnalysis(
            session_id="test", item_category="bulb",
            problem_type="burned_out", confidence=0.9,
            description="A burned-out A19 bulb",
        )

    def _mock_spec_with_questions(self, *args, **kwargs):
        return ProductSpec(
            session_id="test", item_category="bulb",
            attributes={"base_type": "E26", "wattage": 60},
            confidence_per_field={"base_type": 0.9, "wattage": 0.5},
            clarification_questions=["Is this bulb on a dimmer switch?"],
            search_query="E26 60W LED bulb",
        )

    def _mock_spec_no_questions(self, *args, **kwargs):
        return ProductSpec(
            session_id="test", item_category="bulb",
            attributes={"base_type": "E26", "wattage": 60},
            confidence_per_field={"base_type": 0.95, "wattage": 0.9},
            clarification_questions=[],
            search_query="E26 60W LED bulb",
        )

    @patch("src.pipeline.encode_image", return_value=("fake_b64", "image/jpeg"))
    @patch("src.pipeline.vision_analyst.analyze")
    @patch("src.pipeline.spec_extractor.extract")
    @patch("src.pipeline.product_searcher.search")
    @patch("src.pipeline.product_ranker.rank")
    @patch("src.pipeline.save_result")
    def test_start_session_proceeds_with_clarification_questions(self, mock_save, mock_rank, mock_search, mock_extract, mock_analyze, mock_encode):
        mock_analyze.side_effect = self._mock_analysis
        mock_extract.side_effect = self._mock_spec_with_questions
        mock_search.return_value = [ProductResult(title="Bulb", price_cents=500)]
        mock_rank.return_value = [ProductResult(title="Bulb", price_cents=500, rank=1)]

        result = __import__("src.pipeline", fromlist=["start_session"]).start_session("/fake/photo.jpg", "test")

        # Non-blocking: proceeds to RESULTS even with questions
        assert result.stage == PipelineStage.RESULTS
        assert len(result.products) == 1
        mock_search.assert_called_once()

    @patch("src.pipeline.encode_image", return_value=("fake_b64", "image/jpeg"))
    @patch("src.pipeline.vision_analyst.analyze")
    @patch("src.pipeline.spec_extractor.extract")
    @patch("src.pipeline.product_searcher.search")
    @patch("src.pipeline.product_ranker.rank")
    @patch("src.pipeline.save_result")
    def test_start_session_proceeds_without_questions(self, mock_save, mock_rank, mock_search, mock_extract, mock_analyze, mock_encode):
        mock_analyze.side_effect = self._mock_analysis
        mock_extract.side_effect = self._mock_spec_no_questions
        mock_search.return_value = [ProductResult(title="Bulb", price_cents=500)]
        mock_rank.return_value = [ProductResult(title="Bulb", price_cents=500, rank=1)]

        result = __import__("src.pipeline", fromlist=["start_session"]).start_session("/fake/photo.jpg", "test")

        assert result.stage == PipelineStage.RESULTS
        assert len(result.products) == 1
        mock_search.assert_called_once()

    @patch("src.pipeline.product_searcher.search")
    @patch("src.pipeline.product_ranker.rank")
    @patch("src.pipeline.save_result")
    def test_advance_with_clarification_answer(self, mock_save, mock_rank, mock_search):
        # User answers a clarification question from the RESULTS stage
        result = PipelineResult(
            session=Session(photo_path="/fake/photo.jpg"),
            stage=PipelineStage.RESULTS,
            analysis=self._mock_analysis(),
            spec=self._mock_spec_with_questions(),
            products=[ProductResult(title="Old Bulb", price_cents=500)],
        )
        mock_search.return_value = [ProductResult(title="Non-dimmable Bulb", price_cents=500)]
        mock_rank.return_value = [ProductResult(title="Non-dimmable Bulb", price_cents=500, rank=1)]

        from src.pipeline import advance
        result = advance(result, "No, it's not on a dimmer")

        assert result.stage == PipelineStage.RESULTS
        assert len(result.products) == 1
        assert any(m.role == ChatRole.USER and "dimmer" in m.content for m in result.messages)

    @patch("src.pipeline.spec_extractor.extract")
    @patch("src.pipeline.product_searcher.search")
    @patch("src.pipeline.product_ranker.rank")
    @patch("src.pipeline.save_result")
    def test_advance_refinement(self, mock_save, mock_rank, mock_search, mock_extract):
        result = PipelineResult(
            session=Session(photo_path="/fake/photo.jpg"),
            stage=PipelineStage.RESULTS,
            analysis=self._mock_analysis(),
            spec=self._mock_spec_no_questions(),
            products=[ProductResult(title="Old Bulb", price_cents=500)],
        )
        mock_extract.return_value = ProductSpec(
            session_id="test", item_category="bulb",
            attributes={"base_type": "E26", "wattage": 60, "dimmable": True},
            confidence_per_field={"base_type": 0.95, "wattage": 0.9, "dimmable": 0.95},
            search_query="E26 60W LED bulb dimmable",
        )
        mock_search.return_value = [ProductResult(title="Dimmable Bulb", price_cents=700)]
        mock_rank.return_value = [ProductResult(title="Dimmable Bulb", price_cents=700, rank=1)]

        from src.pipeline import advance
        result = advance(result, "I need dimmable")

        assert result.stage == PipelineStage.RESULTS
        assert result.products[0].title == "Dimmable Bulb"
        # Spec was re-extracted with user feedback
        mock_extract.assert_called_once()
        assert "dimmable" in mock_extract.call_args[1].get("extra_context", "") or "dimmable" in str(mock_extract.call_args)
