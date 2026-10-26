"""9 PHC — claim extraction schema.

The JSON Schema handed to Muse Spark (structured output) for the
extraction pass: parse an audited document into a claim list. Every
extracted claim carries its citations exactly as written, plus any
other names its subject carries (the raw material for check 3, the
alias sweep).
"""

EXTRACTION_SCHEMA = {
    "name": "claim_extraction",
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "One discrete checkable statement, verbatim in substance.",
                        },
                        "claim_type": {
                            "type": "string",
                            "enum": ["factual", "numerical", "identity", "existence", "other"],
                        },
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object", "additionalProperties": False,
                                "properties": {
                                    "raw": {"type": "string"},
                                    "source_title": {"type": "string"},
                                    "identifier": {"type": "string"},
                                    "locator": {"type": "string"},
                                },
                                "required": ["raw", "source_title", "identifier", "locator"],
                            },
                        },
                        "aliases": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Other names/titles/labels the claim's subject is known by.",
                        },
                        "numbers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Stated totals in the claim, for check 7.",
                        },
                        "components": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Underlying item values a stated total claims to sum, for check 7.",
                        },
                    },
                    "required": ["text", "claim_type", "citations", "aliases", "numbers", "components"],
                },
            }
        },
        "required": ["claims"],
    },
    "strict": True,
}

EXTRACTION_SYSTEM_PROMPT = """You are the extraction pass of an audit program.
Break the document into discrete, individually checkable claims.
Rules:
- One claim per statement that could be true or false on its own.
- Copy citations EXACTLY as written, including any errors. Never repair them.
- List every other name, title, or label you know the claim's subject carries.
- For numerical claims, record the stated total and the component items it sums.
- Fill EVERY field of the schema; use an empty string or empty list when a claim has none.
- Do not judge the claims. Extraction only."""
