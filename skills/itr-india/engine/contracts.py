from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, TYPE_CHECKING

from jsonschema import SchemaError, ValidationError
from jsonschema.validators import validator_for

from engine.rulebase import RuleReadinessError, RuleTable

if TYPE_CHECKING:
    from engine.trace import Trace


_CONTRACT_ROOT = Path(__file__).with_name("official_contracts")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ASSESSMENT_YEAR = re.compile(r"^[0-9]{4}-[0-9]{2}$")


class OfficialContractValidationError(ValueError):
    """Raised when an official filing contract is absent, corrupt, or violated."""


@dataclass(frozen=True)
class OfficialContract:
    form: str
    assessment_year: str
    schema_version: str
    schema_release_date: date
    schema_source_url: str
    schema_sha256: str
    validation_version: str
    validation_release_date: date
    validation_source_url: str
    validation_sha256: str
    _schema_path: Path
    _validation_path: Path

    def verify_schema_pin(self) -> None:
        self._verify_file_pin(self._schema_path, self.schema_sha256, "schema")

    def verify_validation_pin(self) -> None:
        self._verify_file_pin(
            self._validation_path,
            self.validation_sha256,
            "validation rules",
        )

    def _verify_file_pin(self, path: Path, expected_digest: str, label: str) -> None:
        try:
            digest = sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise OfficialContractValidationError(
                f"Pinned {self.form} {label} cannot be read: {path}"
            ) from exc
        if digest != expected_digest:
            raise OfficialContractValidationError(
                f"Pinned {self.form} {label} checksum mismatch: "
                f"expected {expected_digest}, got {digest}"
            )

    def load_schema(self) -> dict[str, Any]:
        self.verify_schema_pin()
        try:
            return json.loads(self._schema_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OfficialContractValidationError(
                f"Pinned {self.form} schema is not readable JSON"
            ) from exc


class OfficialContractRegistry:
    def __init__(self, manifest_path: Path, *, _rule_table: RuleTable | None = None):
        self._manifest_path = manifest_path
        self._contracts = self._load_manifest(manifest_path)
        self._rule_table = _rule_table

    @classmethod
    def for_assessment_year(cls, assessment_year: str) -> "OfficialContractRegistry":
        if not _ASSESSMENT_YEAR.fullmatch(assessment_year):
            raise OfficialContractValidationError(
                f"Assessment year has invalid format: {assessment_year!r}"
            )
        directory = "ay" + assessment_year.replace("-", "_")
        contract_root = _CONTRACT_ROOT.resolve()
        manifest_path = (contract_root / directory / "manifest.json").resolve()
        if not manifest_path.is_relative_to(contract_root):
            raise OfficialContractValidationError(
                f"Assessment year resolves outside the contract registry: {assessment_year!r}"
            )
        if not manifest_path.is_file():
            raise OfficialContractValidationError(
                f"Official contracts for AY {assessment_year} are not pinned"
            )
        registry = cls(
            manifest_path,
            _rule_table=_authoritative_rule_table(assessment_year),
        )
        if any(
            contract.assessment_year != assessment_year
            for contract in registry.contracts()
        ):
            raise OfficialContractValidationError(
                f"Pinned manifest does not describe AY {assessment_year}"
            )
        return registry

    def contracts(self) -> tuple[OfficialContract, ...]:
        return tuple(self._contracts.values())

    def contract(self, form: str) -> OfficialContract:
        try:
            return self._contracts[form.upper()]
        except KeyError as exc:
            raise OfficialContractValidationError(
                f"Official contract for {form} is not pinned in {self._manifest_path}"
            ) from exc

    def verify_pins(self) -> None:
        for contract in self.contracts():
            contract.verify_schema_pin()
            contract.verify_validation_pin()

    def validate(self, form: str, payload: Any) -> None:
        contract = self.contract(form)
        schema = contract.load_schema()
        validator_class = validator_for(schema)
        try:
            validator_class.check_schema(schema)
            errors = sorted(
                validator_class(schema).iter_errors(payload),
                key=lambda error: tuple(str(part) for part in error.absolute_path),
            )
        except SchemaError as exc:
            raise OfficialContractValidationError(
                f"Pinned {contract.form} contract is not a valid JSON Schema"
            ) from exc
        if errors:
            details = "; ".join(_format_validation_error(error) for error in errors[:10])
            raise OfficialContractValidationError(
                f"Payload violates pinned {contract.form} schema: {details}"
            )

    def validate_filing_package(
        self,
        form: str,
        payload: Any,
        *,
        trace: "Trace",
        on: date,
    ) -> None:
        if self._rule_table is None:
            raise RuleReadinessError(
                "No authoritative rule baseline is bound to this contract registry"
            )
        self._rule_table.require_filing_ready(trace.rule_keys(), on=on)
        self.validate(form, payload)

    @staticmethod
    def _load_manifest(manifest_path: Path) -> dict[str, OfficialContract]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OfficialContractValidationError(
                f"Official contract manifest is unreadable: {manifest_path}"
            ) from exc

        if not isinstance(manifest, dict):
            raise OfficialContractValidationError(
                "Official contract manifest must be a JSON object"
            )
        if manifest.get("manifest_version") != 1:
            raise OfficialContractValidationError("Unsupported official contract manifest version")
        assessment_year = _required_string(manifest, "assessment_year", "manifest")
        raw_contracts = manifest.get("contracts")
        if not isinstance(raw_contracts, list) or not raw_contracts:
            raise OfficialContractValidationError("Contract manifest has no contracts")

        manifest_root = manifest_path.parent.resolve()
        contracts: dict[str, OfficialContract] = {}
        for raw in raw_contracts:
            if not isinstance(raw, dict):
                raise OfficialContractValidationError("Malformed contract manifest entry")
            form = _required_string(raw, "form", "contract").upper()
            schema = _required_mapping(raw, "schema", form)
            validation = _required_mapping(raw, "validation_rules", form)
            schema_path = (manifest_root / _required_string(schema, "local_path", form)).resolve()
            if not schema_path.is_relative_to(manifest_root):
                raise OfficialContractValidationError(
                    f"Pinned {form} schema path escapes the contract directory"
                )
            validation_path = (
                manifest_root / _required_string(validation, "local_path", form)
            ).resolve()
            if not validation_path.is_relative_to(manifest_root):
                raise OfficialContractValidationError(
                    f"Pinned {form} validation path escapes the contract directory"
                )
            schema_digest = _required_digest(schema, "sha256", form)
            validation_digest = _required_digest(validation, "sha256", form)
            if form in contracts:
                raise OfficialContractValidationError(f"Duplicate contract for {form}")
            contracts[form] = OfficialContract(
                form=form,
                assessment_year=assessment_year,
                schema_version=_required_string(schema, "version", form),
                schema_release_date=_required_date(schema, "release_date", form),
                schema_source_url=_required_official_url(schema, "source_url", form),
                schema_sha256=schema_digest,
                validation_version=_required_string(validation, "version", form),
                validation_release_date=_required_date(validation, "release_date", form),
                validation_source_url=_required_official_url(validation, "source_url", form),
                validation_sha256=validation_digest,
                _schema_path=schema_path,
                _validation_path=validation_path,
            )
        return contracts


def _required_mapping(container: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        raise OfficialContractValidationError(f"{context} missing mapping {key!r}")
    return value


def _required_string(container: dict[str, Any], key: str, context: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value:
        raise OfficialContractValidationError(f"{context} missing string {key!r}")
    return value


def _required_date(container: dict[str, Any], key: str, context: str) -> date:
    value = _required_string(container, key, context)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise OfficialContractValidationError(
            f"{context} has invalid date {key!r}: {value!r}"
        ) from exc


def _required_digest(container: dict[str, Any], key: str, context: str) -> str:
    value = _required_string(container, key, context)
    if not _SHA256.fullmatch(value):
        raise OfficialContractValidationError(f"{context} has invalid SHA-256 {key!r}")
    return value


def _required_official_url(container: dict[str, Any], key: str, context: str) -> str:
    value = _required_string(container, key, context)
    if not value.startswith("https://www.incometax.gov.in/"):
        raise OfficialContractValidationError(
            f"{context} {key!r} is not an official Income Tax Department URL"
        )
    return value


def _format_validation_error(error: ValidationError) -> str:
    path = "/" + "/".join(str(part) for part in error.absolute_path)
    return f"{path}: {error.message}"


def _authoritative_rule_table(assessment_year: str) -> RuleTable:
    if assessment_year == "2026-27":
        from engine.rules.ay2026_27 import TABLE

        return TABLE
    raise OfficialContractValidationError(
        f"No authoritative rule baseline is pinned for AY {assessment_year}"
    )
