"""Unit tests for src.schemas.document – UnifiedDocument schema."""

from datetime import date

import pytest
from pydantic import ValidationError
from src.schemas.document import UnifiedDocument

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_payload() -> dict:
    """Minimal valid payload for UnifiedDocument."""
    return {
        "id": "doc_a1b2c3",
        "vin": "1HGCM82633A004352",
        "title": "Vehicle Purchase Agreement",
        "document_type": "contract",
        "source_system": "sales",
        "date": "2024-03-15",
    }


@pytest.fixture
def full_payload(valid_payload: dict) -> dict:
    """Payload with every field populated."""
    return {
        **valid_payload,
        "external_id": "SALE-2024-78432",
        "metadata": {"dealer_name": "AutoNation Honda", "amount": 32500.00},
    }


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestUnifiedDocumentCreation:
    """Test successful model instantiation."""

    def test_minimal_payload(self, valid_payload: dict):
        doc = UnifiedDocument(**valid_payload)

        assert doc.id == "doc_a1b2c3"
        assert doc.vin == "1HGCM82633A004352"
        assert doc.title == "Vehicle Purchase Agreement"
        assert doc.document_type == "contract"
        assert doc.source_system == "sales"
        assert doc.date == date(2024, 3, 15)
        # Defaults
        assert doc.external_id is None
        assert doc.metadata == {}

    def test_full_payload(self, full_payload: dict):
        doc = UnifiedDocument(**full_payload)

        assert doc.external_id == "SALE-2024-78432"
        assert doc.metadata == {"dealer_name": "AutoNation Honda", "amount": 32500.00}

    def test_source_system_sales(self, valid_payload: dict):
        valid_payload["source_system"] = "sales"
        doc = UnifiedDocument(**valid_payload)
        assert doc.source_system == "sales"

    def test_source_system_service(self, valid_payload: dict):
        valid_payload["source_system"] = "service"
        doc = UnifiedDocument(**valid_payload)
        assert doc.source_system == "service"

    def test_date_as_date_object(self, valid_payload: dict):
        valid_payload["date"] = date(2025, 1, 1)
        doc = UnifiedDocument(**valid_payload)
        assert doc.date == date(2025, 1, 1)

    def test_metadata_with_nested_values(self, valid_payload: dict):
        valid_payload["metadata"] = {
            "tags": ["urgent", "vip"],
            "nested": {"key": "value"},
            "count": 42,
        }
        doc = UnifiedDocument(**valid_payload)
        assert doc.metadata["tags"] == ["urgent", "vip"]
        assert doc.metadata["nested"]["key"] == "value"
        assert doc.metadata["count"] == 42


# ---------------------------------------------------------------------------
# Validation / rejection tests
# ---------------------------------------------------------------------------

class TestUnifiedDocumentValidation:
    """Test that invalid data is correctly rejected."""

    @pytest.mark.parametrize("missing_field", [
        "id",
        "vin",
        "title",
        "document_type",
        "source_system",
        "date",
    ])
    def test_required_fields(self, valid_payload: dict, missing_field: str):
        del valid_payload[missing_field]
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any(missing_field in str(e["loc"]) for e in errors)

    def test_invalid_source_system(self, valid_payload: dict):
        valid_payload["source_system"] = "unknown_system"
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any("source_system" in str(e["loc"]) for e in errors)

    def test_invalid_date_format(self, valid_payload: dict):
        valid_payload["date"] = "not-a-date"
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any("date" in str(e["loc"]) for e in errors)

    def test_invalid_date_type(self, valid_payload: dict):
        valid_payload["date"] = 12345
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any("date" in str(e["loc"]) for e in errors)


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestUnifiedDocumentSerialization:
    """Test JSON / dict round-trips."""

    def test_model_dump(self, full_payload: dict):
        doc = UnifiedDocument(**full_payload)
        dumped = doc.model_dump()

        assert isinstance(dumped, dict)
        assert dumped["id"] == "doc_a1b2c3"
        assert dumped["external_id"] == "SALE-2024-78432"
        assert dumped["date"] == date(2024, 3, 15)
        assert dumped["metadata"]["amount"] == 32500.00

    def test_model_dump_json(self, full_payload: dict):
        doc = UnifiedDocument(**full_payload)
        json_str = doc.model_dump_json()

        assert isinstance(json_str, str)
        assert '"id":"doc_a1b2c3"' in json_str.replace(" ", "")
        assert '"date":"2024-03-15"' in json_str.replace(" ", "")

    def test_round_trip_json(self, full_payload: dict):
        """Serialize to JSON and back; result should be identical."""
        original = UnifiedDocument(**full_payload)
        json_str = original.model_dump_json()
        restored = UnifiedDocument.model_validate_json(json_str)

        assert original == restored

    def test_round_trip_dict(self, full_payload: dict):
        """Serialize to dict and back; result should be identical."""
        original = UnifiedDocument(**full_payload)
        data = original.model_dump()
        restored = UnifiedDocument.model_validate(data)

        assert original == restored


# ---------------------------------------------------------------------------
# JSON Schema tests
# ---------------------------------------------------------------------------

class TestUnifiedDocumentJsonSchema:
    """Test that the generated JSON schema has expected structure."""

    def test_json_schema_contains_examples(self):
        schema = UnifiedDocument.model_json_schema()
        assert "examples" in schema

    def test_json_schema_required_fields(self):
        schema = UnifiedDocument.model_json_schema()
        required = schema.get("required", [])
        for field in ("id", "vin", "title", "document_type", "source_system", "date"):
            assert field in required, f"'{field}' should be in 'required'"

    def test_json_schema_source_system_enum(self):
        schema = UnifiedDocument.model_json_schema()
        source_system_prop = schema["properties"]["source_system"]
        assert "enum" in source_system_prop
        assert set(source_system_prop["enum"]) == {"sales", "service"}


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

class TestUnifiedDocumentEdgeCases:
    """Boundary / edge-case scenarios."""

    def test_empty_metadata(self, valid_payload: dict):
        valid_payload["metadata"] = {}
        doc = UnifiedDocument(**valid_payload)
        assert doc.metadata == {}

    def test_external_id_none_explicitly(self, valid_payload: dict):
        valid_payload["external_id"] = None
        doc = UnifiedDocument(**valid_payload)
        assert doc.external_id is None

    def test_extra_fields_ignored_by_default(self, valid_payload: dict):
        valid_payload["unknown_field"] = "should be ignored or raise"
        # Default Pydantic v2 behaviour is to ignore extra fields
        doc = UnifiedDocument(**valid_payload)
        assert not hasattr(doc, "unknown_field")

    def test_empty_string_id(self, valid_payload: dict):
        """An empty string is technically valid unless the schema adds min_length."""
        valid_payload["id"] = ""
        doc = UnifiedDocument(**valid_payload)
        assert doc.id == ""

    def test_very_long_title(self, valid_payload: dict):
        valid_payload["title"] = "A" * 10_000
        doc = UnifiedDocument(**valid_payload)
        assert len(doc.title) == 10_000

    def test_metadata_large_payload(self, valid_payload: dict):
        valid_payload["metadata"] = {f"key_{i}": f"value_{i}" for i in range(100)}
        doc = UnifiedDocument(**valid_payload)
        assert len(doc.metadata) == 100


# ---------------------------------------------------------------------------
# 1a. Explicit None on required fields
# ---------------------------------------------------------------------------

class TestExplicitNoneOnRequiredFields:
    """Passing None explicitly to required fields must raise ValidationError."""

    @pytest.mark.parametrize("field", [
        "id",
        "vin",
        "title",
        "document_type",
        "source_system",
        "date",
    ])
    def test_explicit_none_rejected(self, valid_payload: dict, field: str):
        valid_payload[field] = None
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any(field in str(e["loc"]) for e in errors)


# ---------------------------------------------------------------------------
# 1b. Wrong types for `metadata` (expects Dict[str, Any])
# ---------------------------------------------------------------------------

class TestMetadataWrongType:
    """metadata must be a dict; other types must be rejected."""

    @pytest.mark.parametrize("bad_value, label", [
        ("just a string", "string"),
        (42, "int"),
        (3.14, "float"),
        (True, "bool"),
        (["a", "b"], "list"),
        (("a", "b"), "tuple"),
    ])
    def test_metadata_rejects_non_dict(
        self, valid_payload: dict, bad_value, label: str,
    ):
        valid_payload["metadata"] = bad_value
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any("metadata" in str(e["loc"]) for e in errors), (
            f"metadata should reject {label}: {bad_value!r}"
        )


# ---------------------------------------------------------------------------
# 1c. Non-coercible types on str fields
# ---------------------------------------------------------------------------

class TestStrFieldsRejectNonCoercible:
    """Passing list / dict to str fields must raise ValidationError."""

    STR_FIELDS = ("id", "vin", "title", "document_type")

    @pytest.mark.parametrize("field", STR_FIELDS)
    @pytest.mark.parametrize("bad_value, label", [
        ([1, 2, 3], "list"),
        ({"key": "val"}, "dict"),
    ])
    def test_str_field_rejects_non_coercible(
        self, valid_payload: dict, field: str, bad_value, label: str,
    ):
        valid_payload[field] = bad_value
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any(field in str(e["loc"]) for e in errors), (
            f"Field '{field}' should reject {label}: {bad_value!r}"
        )

    @pytest.mark.parametrize("bad_value, label", [
        ([1, 2, 3], "list"),
        ({"key": "val"}, "dict"),
    ])
    def test_external_id_rejects_non_coercible(
        self, valid_payload: dict, bad_value, label: str,
    ):
        """external_id is Optional[str] but still must not accept list/dict."""
        valid_payload["external_id"] = bad_value
        with pytest.raises(ValidationError) as exc_info:
            UnifiedDocument(**valid_payload)
        errors = exc_info.value.errors()
        assert any("external_id" in str(e["loc"]) for e in errors), (
            f"Field 'external_id' should reject {label}: {bad_value!r}"
        )


# ---------------------------------------------------------------------------
# 2a. json_schema_extra examples validate successfully
# ---------------------------------------------------------------------------

class TestJsonSchemaExtraExamplesValid:
    """Examples embedded in model_config['json_schema_extra'] must be valid."""

    def test_all_examples_validate(self):
        config_extra = UnifiedDocument.model_config.get("json_schema_extra", {})
        examples = config_extra.get("examples", [])
        assert len(examples) > 0, "Expected at least one example in json_schema_extra"

        for idx, example in enumerate(examples):
            doc = UnifiedDocument.model_validate(example)
            # Sanity-check a couple of fields to ensure parsing was meaningful
            assert doc.id, f"Example {idx}: 'id' should be non-empty"
            assert doc.vin, f"Example {idx}: 'vin' should be non-empty"
            assert doc.source_system in ("sales", "service"), (
                f"Example {idx}: unexpected source_system '{doc.source_system}'"
            )


# ---------------------------------------------------------------------------
# 2b. Whitespace-only strings (optional hardening)
# ---------------------------------------------------------------------------

class TestWhitespaceOnlyStrings:
    """Whitespace-only values are accepted unless min_length / validators exist.

    These tests document current behaviour so that adding a strip-whitespace
    validator later won't silently change semantics.
    """

    @pytest.mark.parametrize("field", ["id", "vin", "title", "document_type"])
    def test_whitespace_only_accepted(self, valid_payload: dict, field: str):
        """Current schema has no strip/min_length, so whitespace is accepted."""
        valid_payload[field] = "   "
        doc = UnifiedDocument(**valid_payload)
        assert doc.model_dump()[field] == "   "

    def test_whitespace_only_external_id(self, valid_payload: dict):
        valid_payload["external_id"] = "   "
        doc = UnifiedDocument(**valid_payload)
        assert doc.external_id == "   "
