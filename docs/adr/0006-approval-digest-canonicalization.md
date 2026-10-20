# ADR 0006: approval digest uses an RFC 8785 (JCS) profile

Date: 2026-10-06. Status: Accepted (project owner, decisions D1–D5, 2026-10-06). Amended 2026-10-20 (Phase 3 review, owner accepted; Task 3.D1): observation numbers are rendered as canonical decimal strings (Decision 5).

## Context

MVP design §4 specifies a home-grown canonical JSON: sorted keys, no NaN, canonical decimals, UTF-8, SHA-256. RFC 8785 (JSON Canonicalization Scheme) standardizes almost the same rules: sorted keys by UTF-16 code units, ECMAScript number serialization, no insignificant whitespace, and specific string escaping. It has implementations in Python and TypeScript. Both matter because the overlay UI must be able to show, and optionally re-hash, the exact proposal the approver sees.

## Decision

1. Digest input = JCS (RFC 8785) serialization of a **profile**. Allowed JSON types are objects, arrays, strings, booleans and null. JSON numbers are **forbidden**: money, quantities and integers are strings in the canonical decimal form defined by the contracts. Timestamps are RFC 3339 UTC strings with `Z`.
2. Digest = `sha256` over the UTF-8 bytes. The stored value is `"jcs-sha256-v1:" + lowercase hex`.
3. The profile version (`v1`) is part of the stored digest and of `ApprovalRecord`.
4. A shared golden vector file (input → canonical bytes → digest) lives in the contracts package and is tested by both the Python and the TypeScript implementations.
5. **Observation numbers** (amended 2026-10-20). Provider data can hold JSON numbers. Where the kernel digests or renders it under this profile (the context pack, ADR 0032 §1, and a citation's value, ADR 0033 §1), every number is first written as its canonical decimal string (`number_text`, `contracts/context_pack.py`, through `format_decimal`): no exponent, no trailing zeros, `-0` as `0`, and a float through its shortest round-trip text. A non-finite value, which has no canonical decimal, is written `NaN`, `Infinity` or `-Infinity`. The approval digest input is unchanged: observations enter it only by evidence id, source, revision, completeness and `fact_digest` (`digest_input`, `kernel/approval.py`).

## Alternatives considered

- **Home-grown rules.** They are equivalent in intent, but every edge case (Unicode escaping, key ordering) must be re-derived and tested across languages.
- **Hash a Pydantic `model_dump_json()`.** Output depends on field order and library version.
- **CBOR deterministic encoding.** Sound, but not human-inspectable in the UI or evidence.

## Consequences

- Excluding numbers sidesteps JCS's IEEE-754 number serialization, the usual source of cross-language mismatch.
- Changing the profile requires a new version prefix. Old approvals remain verifiable by their recorded version.

## Verification

- Golden vectors pass in Python and TS, including non-ASCII (Vietnamese) strings and key-ordering cases.
- Property test: semantically equal proposals with different key order or whitespace yield the same digest. Any change to a material field changes it.
