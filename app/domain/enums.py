from enum import StrEnum


class MaterialType(StrEnum):
    TEXT = "text"
    AUDIO = "audio"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    NORMALIZING = "normalizing"
    EXTRACTING = "extracting"
    DEDUPLICATING = "deduplicating"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class EntityKind(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    TOPIC = "topic"
    CLAIM = "claim"
    METRIC = "metric"
    CUSTOM = "custom"


class DashboardAggregateKind(StrEnum):
    MATERIAL_COUNTS = "material_counts"
    INSIGHT_COUNTS = "insight_counts"
    ENTITY_FREQUENCY = "entity_frequency"
    PIPELINE_HEALTH = "pipeline_health"


# --- Step 2: research domain ---


class SourceType(StrEnum):
    """How the source was obtained or classified."""

    UPLOAD = "upload"
    URL = "url"
    API = "api"
    MANUAL = "manual"
    IMPORT = "import"
    OTHER = "other"


class EntityType(StrEnum):
    """Research-level extracted units (primary) + legacy NER-style values for old rows."""

    # --- Primary: interview / UX research units ---
    PROBLEM = "problem"
    PAIN_POINT = "pain_point"
    USER_NEED = "user_need"
    BEHAVIOR_PATTERN = "behavior_pattern"
    TRUST_ISSUE = "trust_issue"
    ADOPTION_BARRIER = "adoption_barrier"
    RISK = "risk"
    HYPOTHESIS = "hypothesis"
    RECOMMENDATION = "recommendation"
    OPPORTUNITY = "opportunity"
    OPEN_QUESTION = "open_question"
    SUPPORTING_FACT = "supporting_fact"
    SENTIMENT_SIGNAL = "sentiment_signal"
    # --- Legacy (older pipelines / DB); do not prefer in new extraction ---
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    TOPIC = "topic"
    CLAIM = "claim"
    METRIC = "metric"
    REFERENCE = "reference"
    CUSTOM = "custom"


class JobStatus(StrEnum):
    """Async job / pipeline lifecycle (e.g. transcription)."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SummaryStatus(StrEnum):
    """Research summary generation state."""

    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    STALE = "stale"
    FAILED = "failed"


class ReportStatus(StrEnum):
    """Structured research report generation lifecycle."""

    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class RelationshipType(StrEnum):
    """Typed edge in the entity graph."""

    RELATED_TO = "related_to"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    PART_OF = "part_of"
    CAUSES = "causes"
    MENTIONS = "mentions"
    SAME_AS = "same_as"
    DERIVED_FROM = "derived_from"
    CUSTOM = "custom"
