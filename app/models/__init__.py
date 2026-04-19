from app.models.base import Base

# Step 2 — research domain (import order matters for mapper configuration)
from app.models.project import Project
from app.models.source_document import SourceDocument
from app.models.source_audio import SourceAudio
from app.models.transcript import Transcript
from app.models.transcript_segment import TranscriptSegment
from app.models.text_chunk import TextChunk
from app.models.entity_relationship import EntityRelationship
from app.models.extracted_entity import ExtractedEntity
from app.models.aggregation_snapshot import AggregationSnapshot
from app.models.research_report import ResearchReport
from app.models.research_summary import ResearchSummary

# Legacy material / insight pipeline
from app.models.dashboard_aggregate import DashboardAggregate
from app.models.insight import Insight
from app.models.insight_source_link import InsightSourceLink
from app.models.material import Material
from app.models.material_extracted_entity import MaterialExtractedEntity

__all__ = [
    "Base",
    "Project",
    "SourceDocument",
    "SourceAudio",
    "Transcript",
    "TranscriptSegment",
    "TextChunk",
    "ExtractedEntity",
    "EntityRelationship",
    "AggregationSnapshot",
    "ResearchReport",
    "ResearchSummary",
    "Material",
    "MaterialExtractedEntity",
    "Insight",
    "InsightSourceLink",
    "DashboardAggregate",
]
